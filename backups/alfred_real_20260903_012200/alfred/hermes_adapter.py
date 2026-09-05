"""Ponte Hermes → Alfred. O chat do Hermes chama isto ANTES do fallback conversacional.
Usa a API Alfred em 127.0.0.1:8791 para um único executor (não duplica estado in-process)."""
import logging
import requests
from .config import get_config
from .confirmations import is_authorization, is_cancel
from .router import is_alfred_message, is_system_control

log = logging.getLogger("alfred.hermes_adapter")


def is_candidate(message: str) -> bool:
    t = (message or "").strip()
    if not t:
        return False
    return is_alfred_message(t) or is_authorization(t) or is_cancel(t) or is_system_control(t)


def _envelope(data: dict, error: bool = False) -> dict:
    job = data.get("job") if isinstance(data, dict) else None
    plan = data.get("plan") if isinstance(data, dict) else None
    status = data.get("status")
    if not status and isinstance(job, dict):
        raw = job.get("status") or ""
        status = {"success": "completed", "waiting_confirmation": "planned",
                  "running": "running", "failed": "failed",
                  "cancelled": "blocked"}.get(raw, raw or "completed")
    if data.get("requires_confirmation") and not status:
        status = "planned"
    if error and not status:
        status = "failed"
    return {
        "route": "alfred",
        "model": (data.get("model") if isinstance(data, dict) else None) or "alfred:qwen3:8b",
        "reply": (data.get("reply") if isinstance(data, dict) else "") or "",
        "plan": plan or {},
        "job_id": (data.get("job_id") if isinstance(data, dict) else "") or (
            (job or {}).get("job_id") if isinstance(job, dict) else "") or "",
        "requires_confirmation": bool(data.get("requires_confirmation")) if isinstance(data, dict) else False,
        "status": status or "completed",
        "job": job,
        "error": bool(error or (isinstance(data, dict) and data.get("error"))),
        "allowed": True,
    }


def handle_hermes_message(message: str, session_id: str = "default", timeout: float = None):
    """Devolve envelope Alfred ou None se a mensagem não é para o executor.
    Falha do Alfred NÃO é transformada em sucesso conversacional."""
    text = str(message or "").strip()
    if not is_candidate(text):
        return None
    cfg = get_config()
    url = f"http://{cfg['host']}:{cfg['port']}/ask"
    try:
        r = requests.post(url, json={"message": text, "session_id": session_id or "default"},
                          timeout=timeout or max(15, int(cfg.get("llm_timeout_s") or 90)))
    except requests.RequestException as e:
        if is_alfred_message(text) or is_system_control(text):
            return _envelope({
                "model": "alfred:qwen3:8b",
                "reply": f"Alfred API indisponível em {url}: {e}",
                "status": "failed",
            }, error=True)
        return None
    if r.status_code == 422:
        return None
    if r.status_code >= 400:
        if is_alfred_message(text) or is_system_control(text):
            return _envelope({
                "model": "alfred:qwen3:8b",
                "reply": f"Alfred HTTP {r.status_code}: {(r.text or '')[:400]}",
                "status": "failed",
            }, error=True)
        return None
    try:
        data = r.json()
    except ValueError:
        return _envelope({
            "model": "alfred:qwen3:8b",
            "reply": f"Alfred devolveu resposta não-JSON: {(r.text or '')[:200]}",
            "status": "failed",
        }, error=True)
    return _envelope(data, error=bool(data.get("error")))
