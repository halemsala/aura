import logging, re, secrets, threading, time
from . import confirmations, router, security
from . import tools  # noqa: F401 — importa para registar todas as ferramentas
from .executor import Executor, JobStore, plan_to_dict
from .ollama_client import OllamaClient, OllamaError, OllamaUnavailable
from .planner import PlanningError, plan_from_dict, plan_from_message

log = logging.getLogger("alfred.bridge")

HELP_TEXT = (
    "Sou o Alfred, assistente local (qwen3:8b), português do Brasil.\n"
    "Visão: 'o que estás a ver', 'olha o desktop', 'olha a tela'.\n"
    "Casa: 'organiza o desktop', 'cria dez pastas de aula 1 até aula 10', "
    "'pesquisa bitcoin e dólar', 'toca uma música', 'coloca na agenda hoje às 14h'.\n"
    "Aura: 'sobe o aura', 'status do aura', 'lista agentes', 'ativa agentes'.\n"
    "GPU: 'exporta worker gpu' — ZIP para o outro PC; depois 'liga worker 192.168.x.x'.\n"
    "Voz Hercules/Humberto neural grave. Mutável = AUTORIZO. Sem apostas reais.\n"
    "Ficheiros: envia no chat (zip, py, md, json, imagem, áudio). "
    "Código Aura: 'procura no aura X', 'lê o código alfred/api.py'. "
    "Melhorias: descreve o que mudar e AUTORIZO — eu patcho C:\\aura, nunca C:\\Windows."
)

CONV_SYSTEM = (
    "Você é o Alfred, assistente pessoal brasileiro — esperto, solto, um pouco debochado no ponto certo, "
    "tipo amigo que resolve as coisas. Fala como gente: 'prontinho', 'vixe', 'tá uma bagunça', "
    "'você merece', 'precisa de mais alguma coisa?'. Humor seco, nunca ofensivo, nunca robô de relatório. "
    "Português do Brasil, 1 a 4 frases faladas, sem markdown, sem listas, sem asteriscos. "
    "Não invente o que não viu na câmara. Não promete lucro. "
    "Se só está conversando, não finja que mexeu no PC."
)

NARRATE_SYS = (
    "Você é o Alfred. Transforme o JSON das ferramentas numa fala curta, humana, em português do Brasil. "
    "Estilo: 'Prontinho.' + o que fez, com nomes reais. Se o desktop está bagunçado: 'Vixe, tá uma bagunça mesmo.' "
    "Termine quase sempre com 'Precisa de mais alguma coisa?'. "
    "Humor leve. NUNCA diga '1 de 1 tarefas'. Se foi dry-run, peça AUTORIZO. "
    "Não invente marcas nem objectos fora do JSON. Sem markdown."
)

_CONV_HINT = re.compile(
    r"[?]|^(?:olá|ola|oi|bom dia|boa tarde|boa noite|quem és|quem e|como estás|como estas|"
    r"o que és|o que fazes|conta|explica|podes ajudar|obrigad|valeu|beleza|e a[ií])\b", re.I)

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


def _memory_ctx() -> str:
    try:
        from .tools.memory import _load
        notes = _load()[-12:]
        if not notes:
            return ""
        return "Memória do utilizador:\n" + "\n".join(
            f"- {e.get('kind')}: {e.get('text')}" for e in notes if e.get("text"))
    except Exception:
        return ""


def _chat_conversation(text: str) -> dict:
    mem = _memory_ctx()
    system = CONV_SYSTEM + (("\n\n" + mem) if mem else "")
    try:
        out = OllamaClient().chat([
            {"role": "system", "content": system},
            {"role": "user", "content": text}],
            temperature=0.45, num_predict=400)
        return _envelope(out.strip() or "(o modelo devolveu resposta vazia)",
                         model="alfred:qwen3:8b", status="completed")
    except OllamaUnavailable as e:
        return _envelope(f"Ollama indisponível, não posso conversar agora: {e}",
                         model="alfred:qwen3:8b", error=True, status="failed")
    except OllamaError as e:
        return _envelope(f"Erro do modelo local: {e}",
                         model="alfred:qwen3:8b", error=True, status="failed")


def _looks_conversational(body: str) -> bool:
    return True


def _narrate_job(user_text: str, job: dict) -> str:
    summary = str(job.get("summary") or "").strip()
    tools = {str(t.get("tool") or "") for t in (job.get("tasks") or [])}
    status_tools = {"system_status", "aura_stack_status", "services_status", "runtime_flags",
                    "list_tools", "gpu_report", "vram_capacity"}
    if summary and (tools <= status_tools or (tools & status_tools and "1 de 1" not in summary)):
        if "1 de 1" not in summary and "tarefas conclu" not in summary.casefold():
            return summary
    results = []
    for t in job.get("tasks") or []:
        results.append({
            "tool": t.get("tool"), "status": t.get("status"),
            "result": t.get("result"), "error": t.get("error"),
        })
    try:
        import json as _json
        out = OllamaClient().chat(
            [{"role": "system", "content": NARRATE_SYS},
             {"role": "user", "content": (
                 f"Pedido: {user_text}\nResultados:\n"
                 + _json.dumps(results, ensure_ascii=False)[:3200])}],
            temperature=0.35, num_predict=320)
        text = (out or "").strip()
        if text and "1 de 1" not in text:
            return text
    except Exception:
        pass
    return job.get("summary") or "Feito."


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
    _maybe_speak(reply, status)
    return out


def _maybe_speak(reply: str, status: str) -> None:
    if not reply or status in ("failed",):
        return
    try:
        from .flags import load_flags
        if not load_flags().get("voice_enabled"):
            return
        text = re.sub(r"\s+", " ", str(reply)).strip()[:400]
        if len(text) < 3:
            return
        threading.Thread(target=_speak_bg, args=(text,), daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


def _speak_bg(text: str) -> None:
    try:
        from .voice_win import speak
        speak(text)
    except Exception:  # noqa: BLE001
        pass


def _submit_and_reply(plan, auth: bool, tok: bool, reason: str, session_id: str,
                      user_text: str = "") -> dict:
    entry = EXECUTOR.submit(plan, authorized=auth, reason=reason, token_ok=tok)
    job = entry["job"]
    STATE.set_last_job(session_id, job["job_id"])
    if job["status"] == "waiting_confirmation":
        return _envelope(
            "Já tens um plano igual pendente. Responde AUTORIZO para executar ou CANCELA.",
            plan=plan_to_dict(plan), job_id=job["job_id"], job=job,
            requires_confirmation=True, status="planned")
    reply = _narrate_job(user_text or plan.intent, job)
    return _envelope(reply, job=job, job_id=job["job_id"],
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
        return _submit_and_reply(plan_from_dict(pending), True, tok, reason, session_id,
                                 user_text=text)

    # 3) prefixo Alfred OU comando de controlo/instalação no chat Hermes
    if not (router.is_alfred_message(text) or router.is_system_control(text)):
        return None
    body = router.strip_prefix(text) or text
    if not body.strip() or router.is_help(body):
        return _envelope(HELP_TEXT, status="completed")

    from .tool_review import is_install_intent
    if is_install_intent(text) or is_install_intent(body):
        return _handle_install(text, body, auth, tok, session_id)

    from . import flags as _flags
    from . import router as _rt
    if (_rt.REPAIR_AURA_RE.match(body) or _rt.normalize(body) == "corrige") and not _flags.load_flags().get("system_repair_allowed"):
        return _envelope(
            "Reparos reais estão DESLIGADOS (por isso as correcções parecem superficiais).\n"
            "Passos: 1) 'Alfred, desativa paper_trade'  2) AUTORIZO  "
            "3) 'Alfred, repara o aura'. execution_allowed continua false (sem apostas reais).",
            status="blocked")

    # 4) planeamento (determinístico primeiro; LLM só para interpretar linguagem)
    try:
        plan = plan_from_message(body, OllamaClient())
    except PlanningError:
        return _chat_conversation(body)

    # 5) decisão de execução: pendente (mostra plano) ou imediata
    if plan.requires_confirmation and not auth:
        STATE.set_pending(session_id, plan_to_dict(plan))
        reply = _plan_summary_text(plan) + "\nResponde AUTORIZO para executar, ou CANCELA para descartar."
        return _envelope(reply, plan=plan_to_dict(plan), request_id=plan.request_id,
                         requires_confirmation=True, status="planned")

    reason = ("autorização no pedido" if auth else "comando único de baixo risco pedido explicitamente") \
             + (" + token local" if tok else "")
    return _submit_and_reply(plan, auth, tok, reason, session_id, user_text=body)


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
