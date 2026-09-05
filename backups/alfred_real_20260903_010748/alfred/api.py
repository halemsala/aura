"""API local do Alfred (FastAPI). Por defeito escuta APENAS em 127.0.0.1.
Endpoints obrigatórios: /health /model /capabilities /memory /ask /plan /execute /cancel /jobs/{id}"""
import argparse, logging, os, sys
from typing import Optional

from . import paths, security, service
from .bridge import EXECUTOR, STORE, STATE, token_ok, try_handle
from .config import get_config
from .executor import Context, plan_to_dict
from .ollama_client import OllamaClient, OllamaUnavailable
from .planner import PlanningError, plan_from_dict, plan_from_message
from .registry import capabilities

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("alfred.api")

try:
    from fastapi import FastAPI, Header, HTTPException
    from pydantic import BaseModel
except ImportError as e:
    print("FALTA DEPENDÊNCIA:", e, "— corre: pip install -r requirements-alfred.txt")
    sys.exit(1)

app = FastAPI(title="Alfred (Aura/Hermes)", version="1.0.0")


class SpeakBody(BaseModel):
    text: str = ""


class AskBody(BaseModel):
    message: str
    session_id: str = "default"
    authorized: bool = False


class PlanBody(BaseModel):
    message: str


class ExecuteBody(BaseModel):
    plan: Optional[dict] = None
    request_id: Optional[str] = None
    authorized: bool = False


class CancelBody(BaseModel):
    job_id: str


@app.on_event("startup")
def _startup():
    service.write_pid()
    cfg = get_config()
    log.info("Alfred API em http://%s:%s (apenas localhost, sem abertura de navegador)",
             cfg["host"], cfg["port"])


@app.on_event("shutdown")
def _shutdown():
    service.clear_pid()


@app.get("/health")
def health():
    cfg = get_config()
    try:
        tags = OllamaClient().tags(timeout=3)
        ollama = {"online": True,
                  "model_present": any(m.get("name") == cfg["model"] for m in tags.get("models", []))}
    except OllamaUnavailable as e:
        ollama = {"online": False, "error": str(e)[:200]}
    from .flags import load_flags
    fl = load_flags()
    return {"status": "ok", "model": cfg["model"], "ollama": ollama,
            "pid": os.getpid(), "host": cfg["host"], "port": cfg["port"],
            "paper_trade": fl.get("paper_trade"), "execution_allowed": False,
            "system_repair_allowed": fl.get("system_repair_allowed"),
            "flags": fl}


@app.post("/voice/speak")
def voice_speak(body: SpeakBody):
    from .voice_win import speak
    return speak(body.text or "")


@app.get("/model")
def model():
    cfg = get_config()
    try:
        installed = OllamaClient().has_model(cfg["model"])
    except OllamaUnavailable:
        installed = None  # Ollama offline — não sabemos; não afirmamos
    return {"model": cfg["model"], "installed": installed,
            "nota": "nunca há fallback silencioso para outro modelo"}


@app.get("/capabilities")
def caps():
    return {"tools": capabilities(), "config": {k: get_config()[k] for k in
            ("paper_trade", "execution_allowed", "max_tasks", "max_retries")}}


@app.get("/tools")
def tools_list():
    from .plugin_loader import load_all_plugins
    from . import paths
    return {"tools": capabilities(), "plugins_dir": str(paths.PLUGINS_DIR),
            "core": sorted(__import__("alfred.registry", fromlist=["CORE_NAMES"]).CORE_NAMES)}


class ToolSourceBody(BaseModel):
    source: str = ""
    path: str = ""
    name: str = ""


@app.post("/tools/review")
def tools_review(body: ToolSourceBody):
    from .tools.tooling import review_tool
    return review_tool({"source": body.source, "path": body.path, "name": body.name},
                       Context("api-review", authorized=False))


@app.post("/tools/install")
def tools_install(body: ToolSourceBody, x_alfred_token: str = Header(default=None)):
    from .tools.tooling import install_tool
    tok = token_ok(x_alfred_token)
    ctx = Context("api-install", authorized=bool(tok), token_ok=tok)
    if ctx.dry():
        return install_tool({"source": body.source, "path": body.path, "name": body.name}, ctx)
    return install_tool({"source": body.source, "path": body.path, "name": body.name}, ctx)


@app.get("/memory")
def memory():
    from .tools import memory as mem
    return mem.memory_search({"query": ""}, Context("api", authorized=False))


@app.post("/ask")
def ask(body: AskBody, x_alfred_token: str = Header(default=None)):
    result = try_handle(body.message, session_id=body.session_id,
                        authorized=body.authorized, token=x_alfred_token)
    if result is None:
        raise HTTPException(422, "mensagem não é para o Alfred (falta prefixo 'Alfred' e não há plano pendente)")
    return result


@app.post("/plan")
def plan(body: PlanBody):
    try:
        p = plan_from_message(body.message, OllamaClient())
    except PlanningError as e:
        raise HTTPException(422, str(e))
    return plan_to_dict(p)


@app.post("/execute")
def execute(body: ExecuteBody, x_alfred_token: str = Header(default=None)):
    tok = token_ok(x_alfred_token)
    auth = body.authorized or tok
    if body.plan:
        try:
            p = plan_from_dict(body.plan)   # revalida TUDO por código
        except PlanningError as e:
            raise HTTPException(422, str(e))
    elif body.request_id:
        entry = STORE.by_request(body.request_id)
        if not entry:
            raise HTTPException(404, "request_id desconhecido")
        job = entry["job"]
        p = plan_from_dict({"request_id": job["request_id"], "intent": job["plan_intent"],
                            "source_message": job["source_message"],
                            "tasks": [{"tool": t["tool"], "arguments": t["arguments"]} for t in job["tasks"]]})
    else:
        raise HTTPException(422, "envia 'plan' ou 'request_id' no corpo")
    entry = EXECUTOR.submit(p, authorized=auth, reason="execução via API local", token_ok=tok)
    return {"model": "alfred:qwen3:8b", "reply": entry["job"]["summary"], "job": entry["job"]}


@app.post("/cancel")
def cancel(body: CancelBody):
    if not EXECUTOR.cancel(body.job_id):
        raise HTTPException(404, "job desconhecido")
    return {"cancelled": True, "job": STORE.get(body.job_id)["job"]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    entry = STORE.get(job_id)
    if not entry:
        raise HTTPException(404, "job desconhecido")
    return entry["job"]


def main():
    ap = argparse.ArgumentParser(prog="alfred.api")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    a = ap.parse_args()
    cfg = get_config()
    host = a.host or cfg["host"]
    port = a.port or cfg["port"]
    if host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("ALFRED_ALLOW_LAN") != "1":
        print("RECUSADO: a API só escuta em localhost por defeito.")
        print("Para expor à LAN (NÃO recomendado) define a variável de ambiente ALFRED_ALLOW_LAN=1.")
        sys.exit(1)
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
