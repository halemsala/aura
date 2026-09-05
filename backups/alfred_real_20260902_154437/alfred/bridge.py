import logging, re, secrets, threading, time
from . import confirmations, router, security
from . import tools  # noqa: F401 — importa para registar todas as ferramentas
from .executor import Executor, JobStore, plan_to_dict
from .ollama_client import OllamaClient, OllamaError, OllamaUnavailable
from .planner import PlanningError, plan_from_dict, plan_from_message

log = logging.getLogger("alfred.bridge")

HELP_TEXT = (
    "Sou o Alfred, a camada de comandos do Aura/Hermes (modelo local qwen3:8b).\n"
    "Exemplos:\n"
    "  'abre três pesquisas sobre automação'  -> plano de 3 URLs, executa com AUTORIZO\n"
    "  'abre exemplo.com'                     -> abre de imediato (pedido explícito, risco baixo)\n"
    "  'cria pasta Projectos 2025'            -> cria em Desktop (risco baixo)\n"
    "  'lista ficheiros' / 'organiza desktop' -> leitura imediata / plano com AUTORIZO\n"
    "  'lembra-te que reunião amanhã às 10'   -> guarda nota (dados pessoais só após AUTORIZO)\n"
    "  'o que sabes sobre X'                  -> pesquisa a memória local\n"
    "  'estado' / 'diagnóstico' / 'check ollama' -> leitura/diagnóstico, sem confirmação\n"
    "  'cria checkpoint' / 'restaura checkpoint' -> backup / restauro (restauro exige execução autorizada)\n"
    "Regras: nada é executado por iniciativa própria; tarefas com efeitos mostram o plano antes; "
    "autoriza 'AUTORIZO', 'executa' ou 'faz agora'; cancela com 'cancela'."
)

CONV_SYSTEM = (
    "És o Alfred, assistente local do projecto Aura/Hermes, a correr com o modelo qwen3:8b no Ollama local. "
    "Responde em português de Portugal, curto e directo. Nunca afirmes que executaste acções no computador: "
    "tu só conversas; acções reais só acontecem através de um plano autorizado com AUTORIZO."
)

_CONV_HINT = re.compile(
    r"[?]|^(?:olá|ola|oi|bom dia|boa tarde|boa noite|quem és|quem e|como estás|como estas|"
    r"o que és|o que fazes|conta|explica|fala|podes ajudar)\b", re.I)

_TTL = 900.0  # planos pendentes expiram após 15 minutos


class _SessionState:
    def __init__(self):
        self.lock = threading.Lock()
        self.pending_plans = {}   # session_id -> {"plan": dict, "ts": float}
        self.last_job = {}        # session_id -> job_id

    def set_pending(self, sid, plan_dict):
        with self.lock:
            self.pending_plans[sid] = {"plan": plan_dict, "ts": time.time()}

    def pop_pending(self, sid):
        with self.lock:
            e = self.pending_plans.pop(sid, None)
        if e and time.time() - e["ts"] <= _TTL:
            return e["plan"]
        return None

    def peek_pending(self, sid):
        with self.lock:
            e = self.pending_plans.get(sid)
        if e and time.time() - e["ts"] <= _TTL:
            return e["plan"]
        return None

    def set_last_job(self, sid, job_id):
        with self.lock:
            self.last_job[sid] = job_id

    def get_last_job(self, sid):
        with self.lock:
            return self.last_job.get(sid)


STATE = _SessionState()
STORE = JobStore()
EXECUTOR = Executor(STORE)


def token_ok(token) -> bool:
    """Valida o token local (X-Alfred-Token) contra data/alfred/local_token."""
    if not token:
        return False
    try:
        return secrets.compare_digest(str(token), security.get_local_token())
    except Exception:  # noqa: BLE001
        return False


def _plan_summary_text(plan) -> str:
    lines = [f"Plano criado: {len(plan.tasks)} tarefa(s)."]
    for t in plan.tasks:
        arg = ", ".join(f"{k}={str(v)[:60]}" for k, v in t.arguments.items())
        lines.append(f"  {t.id}. {t.tool}({arg}) [risco {t.risk}]")
    return "\n".join(lines)


def _chat_conversation(text: str) -> dict:
    try:
        out = OllamaClient().chat([
            {"role": "system", "content": CONV_SYSTEM},
            {"role": "user", "content": text}])
        return {"model": "qwen3:8b", "reply": out.strip() or "(o modelo devolveu resposta vazia)",
                "allowed": True}
    except OllamaUnavailable as e:
        return {"model": "qwen3:8b", "reply": f"Ollama indisponível, não posso conversar agora: {e}",
                "error": True, "allowed": True}
    except OllamaError as e:
        return {"model": "qwen3:8b", "reply": f"Erro do modelo local: {e}", "error": True, "allowed": True}


def _looks_conversational(body: str) -> bool:
    return bool(_CONV_HINT.search(body or ""))


def _submit_and_reply(plan, auth: bool, tok: bool, reason: str, session_id: str) -> dict:
    entry = EXECUTOR.submit(plan, authorized=auth, reason=reason, token_ok=tok)
    job = entry["job"]
    STATE.set_last_job(session_id, job["job_id"])
    if job["status"] == "waiting_confirmation":
        return {"model": "alfred:qwen3:8b",
                "reply": "Já tens um plano igual pendente. Responde AUTORIZO para executar ou CANCELA.",
                "plan": plan_to_dict(plan), "job_id": job["job_id"],
                "requires_confirmation": True, "allowed": True}
    return {"model": "alfred:qwen3:8b", "reply": job["summary"], "job": job,
            "job_id": job["job_id"], "allowed": True}


def try_handle(message: str, session_id: str = "default", authorized: bool = False,
               token: str = None):
    """PONTO DE INTEGRAÇÃO ÚNICO no Hermes.

    Chamar ANTES do fallback conversacional do LLM.
    Devolve None se a mensagem não é para o Alfred (o Hermes segue o seu fluxo normal).
    Devolve dict com reply/model/plan/job caso contrário.
    Nunca lança excepções — o chat do Hermes não deve rebentar por causa do Alfred.
    """
    try:
        return _handle(message, session_id, authorized, token)
    except Exception as e:  # noqa: BLE001
        log.exception("erro interno do Alfred")
        return {"model": "alfred:qwen3:8b",
                "reply": f"Erro interno do Alfred: {type(e).__name__}: {e}",
                "error": True, "allowed": True}


def _handle(message, session_id, authorized, token):
    text = str(message or "").strip()
    if not text:
        return None
    tok = token_ok(token)
    auth = bool(authorized) or tok

    # 1) cancelamento (só se houver algo do Alfred activo)
    if confirmations.is_cancel(text):
        pending = STATE.peek_pending(session_id)
        job_id = STATE.get_last_job(session_id)
        if not pending and not job_id:
            return None  # não é para o Alfred
        STATE.pop_pending(session_id)
        if job_id:
            EXECUTOR.cancel(job_id)
            entry = STORE.get(job_id)
            reply = "Cancelado. " + (entry["job"]["summary"] or "") if entry else "Cancelado."
            return {"model": "alfred:qwen3:8b", "reply": reply, "job_id": job_id, "allowed": True}
        return {"model": "alfred:qwen3:8b", "reply": "Plano pendente descartado. Nada foi executado.",
                "allowed": True}

    # 2) autorização de um plano pendente
    if confirmations.is_authorization(text):
        pending = STATE.pop_pending(session_id)
        if not pending:
            return None  # AUTORIZO sem plano do Alfred — deixa o Hermes tratar
        reason = "AUTORIZO escrito pelo utilizador" + (" + token local" if tok else "")
        return _submit_and_reply(plan_from_dict(pending), True, tok, reason, session_id)

    # 3) prefixo Alfred
    if not router.is_alfred_message(text):
        return None
    body = router.strip_prefix(text)
    if not body or router.is_help(body):
        return {"model": "alfred:qwen3:8b", "reply": HELP_TEXT, "allowed": True}

    # 4) planeamento (determinístico primeiro; LLM só para interpretar linguagem)
    try:
        plan = plan_from_message(body, OllamaClient())
    except PlanningError as e:
        if _looks_conversational(body):
            return _chat_conversation(body)
        return {"model": "alfred:qwen3:8b",
                "reply": f"Não consegui transformar o pedido em tarefas seguras: {e}",
                "error": True, "allowed": True}

    # 5) decisão de execução: pendente (mostra plano) ou imediata
    if plan.requires_confirmation and not auth:
        STATE.set_pending(session_id, plan_to_dict(plan))
        reply = _plan_summary_text(plan) + "\nResponde AUTORIZO para executar, ou CANCELA para descartar."
        return {"model": "alfred:qwen3:8b", "reply": reply, "plan": plan_to_dict(plan),
                "request_id": plan.request_id, "requires_confirmation": True, "allowed": True}

    reason = ("autorização no pedido" if auth else "comando único de baixo risco pedido explicitamente") \
             + (" + token local" if tok else "")
    return _submit_and_reply(plan, auth, tok, reason, session_id)
