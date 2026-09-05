import logging, re, secrets, threading, time
from . import confirmations, router, security
from . import tools  # noqa: F401 — importa para registar todas as ferramentas
from .executor import Executor, JobStore, plan_to_dict
from .ollama_client import OllamaClient, OllamaError, OllamaUnavailable
from .planner import PlanningError, plan_from_dict, plan_from_message

log = logging.getLogger("alfred.bridge")

HELP_TEXT = (
    "Sou o Alfred, executor do Aura/Hermes (qwen3:8b).\n"
    "Controlo: estado, diagnóstico, gpu, serviços, flags, config, logs, jobs, ferramentas.\n"
    "Instalar ferramenta: cola o código Python com o contrato TOOL_NAME/validate/run "
    "e escreve 'Alfred, instala esta ferramenta' + bloco ```python ... ```. "
    "Eu revejo, peço AUTORIZO, instalo e revejo outra vez. Rollback se a pós-revisão falhar.\n"
    "Outros: 'lista ferramentas', 'desinstala ferramenta NOME', 'recarrega plugins'.\n"
    "Mutável exige AUTORIZO. paper_trade e execution_allowed não são alteráveis por ferramentas."
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
        return _envelope(out.strip() or "(o modelo devolveu resposta vazia)",
                         model="alfred:qwen3:8b", status="completed")
    except OllamaUnavailable as e:
        return _envelope(f"Ollama indisponível, não posso conversar agora: {e}",
                         model="alfred:qwen3:8b", error=True, status="failed")
    except OllamaError as e:
        return _envelope(f"Erro do modelo local: {e}",
                         model="alfred:qwen3:8b", error=True, status="failed")


def _looks_conversational(body: str) -> bool:
    return bool(_CONV_HINT.search(body or ""))


def _status_from_job(job: dict, requires_confirmation: bool = False) -> str:
    raw = (job or {}).get("status") or ""
    mapping = {"success": "completed", "waiting_confirmation": "planned",
               "running": "running", "failed": "failed", "cancelled": "blocked"}
    if requires_confirmation and raw in ("", "waiting_confirmation"):
        return "planned"
    return mapping.get(raw, raw or "completed")


def _envelope(reply: str, **kw) -> dict:
    job = kw.get("job")
    plan = kw.get("plan") or {}
    requires = bool(kw.get("requires_confirmation"))
    status = kw.get("status")
    if not status:
        status = _status_from_job(job, requires) if job else ("failed" if kw.get("error") else (
            "planned" if requires else "completed"))
    out = {
        "route": "alfred",
        "model": kw.get("model") or "alfred:qwen3:8b",
        "reply": reply,
        "plan": plan,
        "job_id": kw.get("job_id") or ((job or {}).get("job_id") if isinstance(job, dict) else "") or "",
        "requires_confirmation": requires,
        "status": status,
        "allowed": True,
    }
    if job is not None:
        out["job"] = job
    if kw.get("error"):
        out["error"] = True
    if kw.get("request_id"):
        out["request_id"] = kw["request_id"]
    return out


def _submit_and_reply(plan, auth: bool, tok: bool, reason: str, session_id: str) -> dict:
    entry = EXECUTOR.submit(plan, authorized=auth, reason=reason, token_ok=tok)
    job = entry["job"]
    STATE.set_last_job(session_id, job["job_id"])
    if job["status"] == "waiting_confirmation":
        return _envelope(
            "Já tens um plano igual pendente. Responde AUTORIZO para executar ou CANCELA.",
            plan=plan_to_dict(plan), job_id=job["job_id"], job=job,
            requires_confirmation=True, status="planned")
    return _envelope(job["summary"], job=job, job_id=job["job_id"],
                     plan=plan_to_dict(plan), status=_status_from_job(job))


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
        return _envelope(f"Erro interno do Alfred: {type(e).__name__}: {e}",
                         error=True, status="failed")


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
            return _envelope(reply, job_id=job_id, status="blocked")
        return _envelope("Plano pendente descartado. Nada foi executado.", status="blocked")

    # 2) autorização de um plano pendente
    if confirmations.is_authorization(text):
        pending = STATE.pop_pending(session_id)
        if not pending:
            return None  # AUTORIZO sem plano do Alfred — deixa o Hermes tratar
        reason = "AUTORIZO escrito pelo utilizador" + (" + token local" if tok else "")
        return _submit_and_reply(plan_from_dict(pending), True, tok, reason, session_id)

    # 3) prefixo Alfred OU comando de controlo/instalação no chat Hermes
    if not (router.is_alfred_message(text) or router.is_system_control(text)):
        return None
    body = router.strip_prefix(text) or text
    if not body.strip() or router.is_help(body):
        return _envelope(HELP_TEXT, status="completed")

    from .tool_review import extract_code, is_install_intent, review_source, write_review
    if is_install_intent(text) or is_install_intent(body):
        return _handle_install(text, body, auth, tok, session_id)

    # 4) planeamento (determinístico primeiro; LLM só para interpretar linguagem)
    try:
        plan = plan_from_message(body, OllamaClient())
    except PlanningError as e:
        if _looks_conversational(body):
            return _chat_conversation(body)
        return _envelope(f"Não consegui transformar o pedido em tarefas seguras: {e}",
                         error=True, status="failed")

    # 5) decisão de execução: pendente (mostra plano) ou imediata
    if plan.requires_confirmation and not auth:
        STATE.set_pending(session_id, plan_to_dict(plan))
        reply = _plan_summary_text(plan) + "\nResponde AUTORIZO para executar, ou CANCELA para descartar."
        return _envelope(reply, plan=plan_to_dict(plan), request_id=plan.request_id,
                         requires_confirmation=True, status="planned")

    reason = ("autorização no pedido" if auth else "comando único de baixo risco pedido explicitamente") \
             + (" + token local" if tok else "")
    return _submit_and_reply(plan, auth, tok, reason, session_id)


def _handle_install(text, body, auth, tok, session_id):
    from . import paths, tool_review
    from .planner import Plan
    from .executor import Task
    from .registry import TOOLS
    from .util import jsonable
    code = tool_review.extract_code(text) or tool_review.extract_code(body)
    if not code:
        return _envelope(
            "Para instalar uma ferramenta cola o código num bloco:\n"
            "Alfred, instala esta ferramenta\n```python\nTOOL_NAME = \"minha_tool\"\n"
            "...\ndef validate(args): ...\ndef run(args, ctx): ...\n```\n"
            "Contrato: ver alfred/tools/plugins/_TEMPLATE.py. Revisão primeiro, AUTORIZO depois.",
            status="planned")
    report = tool_review.review_source(code)
    report_path = tool_review.write_review(report)
    if not report.get("ok"):
        blockers = "\n".join(f"- {b}" for b in report.get("blockers") or [])
        return _envelope(
            f"Revisão PRE-INSTALL recusou o código (nada foi instalado).\n{blockers}\n"
            f"Relatório: {report_path}",
            error=True, status="failed", plan={"review": report})
    name = report["manifest"]["name"]
    stage = paths.STAGING_DIR / f"{name}.py"
    paths.STAGING_DIR.mkdir(parents=True, exist_ok=True)
    stage.write_text(code, encoding="utf-8")
    spec = TOOLS["install_tool"]
    task = Task(id="task-1", tool="install_tool",
                arguments=jsonable({"path": str(stage), "name": name}),
                risk=spec.risk, mutating=True)
    plan = Plan(request_id="inst-"+name[:12], intent="install_tool",
                requires_confirmation=True, tasks=[task], created_from=body[:300],
                content_hash="inst-"+name)
    warn = report.get("warnings") or []
    extra = ("\nAvisos:\n" + "\n".join(f"- {w}" for w in warn)) if warn else ""
    if not auth:
        STATE.set_pending(session_id, plan_to_dict(plan))
        return _envelope(
            f"Revisão PRE-INSTALL OK para '{name}' (risk={report['manifest'].get('risk')})."
            f"{extra}\nRelatório: {report_path}\n"
            "Responde AUTORIZO para instalar e correr a pós-revisão, ou CANCELA.",
            plan=plan_to_dict(plan), requires_confirmation=True, status="planned")
    return _submit_and_reply(plan, True, tok, "instalação autorizada", session_id)
