import json, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field, asdict
from . import paths, util
from .config import get_config
from .registry import TOOLS


class ToolError(RuntimeError):
    pass


@dataclass
class Task:
    id: str
    tool: str
    arguments: dict
    risk: str
    status: str = "planned"          # planned|waiting_confirmation|running|success|failed|skipped|rolled_back
    result: dict = field(default_factory=dict)
    error: str = ""
    attempts: int = 0


@dataclass
class Plan:
    request_id: str
    intent: str
    requires_confirmation: bool
    tasks: list                       # list[Task]
    created_from: str = ""
    content_hash: str = ""


def plan_to_dict(plan: Plan) -> dict:
    return {
        "request_id": plan.request_id,
        "intent": plan.intent,
        "requires_confirmation": plan.requires_confirmation,
        "tasks": [asdict(t) for t in plan.tasks],
    }


class Context:
    """Contexto por job passado a cada ferramenta."""

    def __init__(self, job_id: str, authorized: bool, token_ok: bool = False):
        self.job_id = job_id
        self.authorized = bool(authorized)
        self.token_ok = bool(token_ok)
        self.current_spec = None
        self._cancel = threading.Event()
        self._lines = []

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self):
        self._cancel.set()

    def strong_auth(self) -> bool:
        cfg = get_config()
        return self.authorized and (bool(cfg.get("execution_allowed")) or self.token_ok)

    def dry(self, spec=None) -> bool:
        """True = a ferramenta NÃO deve produzir efeitos reais."""
        spec = spec or self.current_spec
        if spec is None or not spec.mutating:
            return False
        return not self.authorized

    def log(self, line: str):
        self._lines.append(line[:200])


def human_summary(job: dict) -> str:
    tasks = job["tasks"]
    if job["status"] == "cancelled":
        done = sum(1 for t in tasks if t["status"] == "success")
        return f"Cancelado: {done} de {len(tasks)} tarefas concluídas antes da interrupção."
    ok = [t for t in tasks if t["status"] == "success"]
    fails = [t for t in tasks if t["status"] == "failed"]
    skipped = [t for t in tasks if t["status"] == "skipped"]
    all_dry = bool(ok) and all(t.get("result", {}).get("dry_run") for t in ok)
    if job.get("plan_intent") == "search_multi" or (tasks and all(t["tool"] == "open_url" for t in tasks)):
        base = f"{len(ok)} de {len(tasks)} pesquisas abertas com sucesso."
    else:
        base = f"{len(ok)} de {len(tasks)} tarefas concluídas com sucesso."
    if all_dry:
        base += " Executado em dry-run: nada foi alterado. Responde AUTORIZO para executar a sério."
    parts = [base]
    for t in fails:
        parts.append(f"FALHOU {t['id']} ({t['tool']}): {t['error']}")
    if fails and skipped:
        parts.append(f"{len(skipped)} tarefa(s) seguinte(s) saltada(s) por segurança.")
    elif skipped:
        for t in skipped:
            parts.append(f"{t['id']} saltada: {t['error']}")
    return " ".join(parts)


class JobStore:
    def __init__(self):
        self._jobs = {}
        self._by_request = {}
        self._by_hash = {}
        self._lock = threading.Lock()

    def create(self, plan: Plan, authorized: bool, reason: str, token_ok: bool = False) -> dict:
        cooldown = int(get_config().get("request_cooldown_s", 60))
        now = time.time()
        with self._lock:
            prev = self._by_hash.get(plan.content_hash)
            if prev and now - prev["job"]["created_at"] < cooldown \
                    and prev["job"]["status"] in ("running", "waiting_confirmation"):
                prev["job"]["dedupe_hits"] = prev["job"].get("dedupe_hits", 0) + 1
                self.save(prev)
                return prev
            job = {
                "job_id": uuid.uuid4().hex[:12],
                "request_id": plan.request_id,
                "content_hash": plan.content_hash,
                "created_at": now,
                "status": "waiting_confirmation" if (plan.requires_confirmation and not authorized) else "running",
                "authorized": bool(authorized),
                "authorization_reason": reason,
                "plan_intent": plan.intent,
                "source_message": (plan.created_from or "")[:300],
                "dedupe_hits": 0,
                "tasks": [asdict(t) for t in plan.tasks],
                "summary": "",
            }
            entry = {"job": job, "ctx": Context(job["job_id"], authorized=authorized, token_ok=token_ok)}
            self._jobs[job["job_id"]] = entry
            self._by_request[plan.request_id] = entry
            self._by_hash[plan.content_hash] = entry
            self.save(entry)
            return entry

    def get(self, job_id: str):
        return self._jobs.get(job_id)

    def by_request(self, request_id: str):
        return self._by_request.get(request_id)

    def save(self, entry: dict):
        util.atomic_write_json(paths.JOBS_DIR / f"{entry['job']['job_id']}.json", entry["job"])


class Executor:
    def __init__(self, store: JobStore):
        self.store = store

    def submit(self, plan: Plan, authorized: bool, reason: str, token_ok: bool = False) -> dict:
        entry = self.store.create(plan, authorized, reason, token_ok)
        if entry["job"]["status"] == "running":
            self.run(entry)
        return entry

    def cancel(self, job_id: str) -> bool:
        entry = self.store.get(job_id)
        if not entry:
            return False
        entry["ctx"].cancel()
        for t in entry["job"]["tasks"]:
            if t["status"] in ("planned", "waiting_confirmation"):
                t["status"] = "skipped"
                t["error"] = "cancelado pelo utilizador"
        entry["job"]["status"] = "cancelled"
        entry["job"]["summary"] = human_summary(entry["job"])
        self.store.save(entry)
        return True

    def run(self, entry: dict) -> dict:
        cfg = get_config()
        job, ctx = entry["job"], entry["ctx"]
        job["status"] = "running"
        self.store.save(entry)
        failure = None
        for t in job["tasks"]:
            if ctx.cancelled():
                if t["status"] in ("planned", "waiting_confirmation"):
                    t["status"] = "skipped"
                    t["error"] = "cancelado pelo utilizador"
                continue
            if failure is not None:
                t["status"] = "skipped"
                t["error"] = f"saltada: {failure['id']} ({failure['tool']}) falhou antes"
                continue
            spec = TOOLS.get(t["tool"])
            if spec is None:
                t["status"] = "failed"
                t["error"] = f"ferramenta desconhecida: {t['tool']}"
                failure = {"id": t["id"], "tool": t["tool"]}
                self.store.save(entry)
                continue
            t["status"] = "running"
            t["attempts"] = 0
            self.store.save(entry)
            err = None
            max_retries = int(cfg.get("max_retries", 2))
            for attempt in range(1, (1 + max_retries) + 1):
                t["attempts"] = attempt
                if ctx.cancelled():
                    err = "cancelado"
                    break
                try:
                    t["result"] = self._call(spec, t, ctx, cfg)
                    err = None
                    break
                except Exception as e:  # noqa: BLE001 — falhas de ferramenta são registadas, nunca engolidas
                    err = f"{type(e).__name__}: {e}"
                    if attempt <= max_retries:
                        time.sleep(0.4 * attempt)
            if err == "cancelado":
                t["status"] = "skipped"
                t["error"] = "cancelado pelo utilizador"
                continue
            if err is None:
                t["status"] = "success"
            else:
                t["status"] = "failed"
                t["error"] = err
                failure = {"id": t["id"], "tool": t["tool"]}
                self._maybe_rollback(spec, t, ctx)
            self.store.save(entry)
        any_fail = any(t["status"] == "failed" for t in job["tasks"])
        job["status"] = "cancelled" if ctx.cancelled() else ("failed" if any_fail else "success")
        job["finished_at"] = time.time()
        job["summary"] = human_summary(job)
        self.store.save(entry)
        return entry

    def _call(self, spec, t: dict, ctx: Context, cfg: dict) -> dict:
        if spec.mutating and ctx.authorized and spec.sensitive and not ctx.strong_auth():
            raise ToolError(
                "ferramenta sensível bloqueada: define execution_allowed=true em config/alfred.json "
                "ou fornece o token local (X-Alfred-Token)")
        ctx.current_spec = spec
        timeout = float(cfg.get("task_timeout_s", 30))
        ex = ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(spec.fn, t["arguments"], ctx)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeout:
            ctx.cancel()
            ex.shutdown(wait=False, cancel_futures=True)
            raise ToolError(f"timeout da tarefa após {timeout}s")
        finally:
            ex.shutdown(wait=False)

    def _maybe_rollback(self, spec, t: dict, ctx: Context):
        if spec.rollback is None:
            return
        try:
            if spec.rollback(t["arguments"], t.get("result") or {}, ctx):
                t["status"] = "rolled_back"
        except Exception as e:  # noqa: BLE001
            ctx.log(f"rollback de {t['id']} falhou: {e}")
