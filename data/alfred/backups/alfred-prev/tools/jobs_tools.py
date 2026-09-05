"""Gestão de jobs Alfred: listar e cancelar."""
from ..executor import human_summary
from ..registry import ToolSpec, register
from ..validators import ValidationError


def _v0(args) -> dict:
    return {}


def list_jobs(args, ctx) -> dict:
    from ..bridge import STORE
    jobs = []
    for entry in list(STORE._jobs.values())[-50:]:
        job = entry.get("job") or {}
        jobs.append({
            "job_id": job.get("job_id"),
            "status": job.get("status"),
            "intent": job.get("plan_intent"),
            "summary": job.get("summary"),
            "source": (job.get("source_message") or "")[:120],
            "tasks": [{"id": t.get("id"), "tool": t.get("tool"), "status": t.get("status")}
                      for t in (job.get("tasks") or [])],
        })
    return {"count": len(jobs), "jobs": jobs}


def _v_cancel(args) -> dict:
    job_id = str((args or {}).get("job_id") or "").strip()
    if not job_id or len(job_id) > 40:
        raise ValidationError("job_id inválido")
    return {"job_id": job_id}


def cancel_job(args, ctx) -> dict:
    a = _v_cancel(args)
    from ..bridge import EXECUTOR, STORE
    ok = EXECUTOR.cancel(a["job_id"])
    entry = STORE.get(a["job_id"])
    job = (entry or {}).get("job") or {}
    if not ok:
        return {"cancelled": False, "job_id": a["job_id"], "error": "job desconhecido"}
    return {"cancelled": True, "job_id": a["job_id"], "summary": job.get("summary") or human_summary(job)}


register(ToolSpec("list_jobs", list_jobs, _v0, risk="low", mutating=False,
                  summary="Lista jobs recentes do Alfred (só leitura)"))
register(ToolSpec("cancel_job", cancel_job, _v_cancel, risk="low", mutating=True,
                  summary="Cancela um job pelo id"))
