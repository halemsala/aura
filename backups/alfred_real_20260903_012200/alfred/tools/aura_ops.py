"""Alfred gere agentes e serviços AURA (localhost, paper-only)."""
from __future__ import annotations

import sys

import requests

from .. import paths
from ..registry import ToolSpec, register
from ..validators import ValidationError

ENGINE = "http://127.0.0.1:8765"
MATRIZ = "http://127.0.0.1:8766"
BRIDGE = "http://127.0.0.1:8080"
VOICE = "http://127.0.0.1:8099"
HERMES = "http://127.0.0.1:8777"

RESTARTABLE = ("engine", "bridge", "matriz", "voice", "voz", "core")


def _v0(args) -> dict:
    return {}


def _ping(url: str, timeout: float = 3.0):
    try:
        r = requests.get(url, timeout=timeout)
        return {"online": r.status_code < 500, "status": r.status_code}
    except requests.RequestException as e:
        return {"online": False, "error": str(e)[:120]}


def aura_stack_status(args, ctx) -> dict:
    return {
        "bridge": _ping(BRIDGE + "/health"),
        "engine": _ping(ENGINE + "/api/health"),
        "matriz": _ping(MATRIZ + "/health"),
        "voice": _ping(VOICE + "/api/voice/health"),
        "hermes": _ping(HERMES + "/health"),
        "alfred": {"online": True, "nota": "este processo"},
        "ollama": _ping("http://127.0.0.1:11434/api/tags"),
        "execution_allowed": False,
        "idioma": "pt-BR",
    }


register(ToolSpec("aura_stack_status", aura_stack_status, _v0, risk="low", mutating=False,
                  summary="Estado Bridge/Engine/Matriz/Voz/Hermes/Ollama"))


def aura_agents_list(args, ctx) -> dict:
    try:
        r = requests.get(ENGINE + "/api/agents", timeout=6)
        data = r.json() if r.ok else {}
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)[:160]}
    agents = data.get("agents") or data.get("items") or []
    if isinstance(agents, dict):
        agents = [{"id": k, **(v if isinstance(v, dict) else {"value": v})} for k, v in agents.items()]
    summary = []
    for a in agents[:80]:
        if not isinstance(a, dict):
            continue
        summary.append({
            "id": a.get("id") or a.get("agent_id") or a.get("name"),
            "status": a.get("status"),
            "state": a.get("implementation_state") or a.get("state"),
            "runnable": a.get("runnable_functions") or a.get("functions") or [],
        })
    return {
        "ok": True,
        "count": len(summary),
        "agents": summary,
        "engine": {"status": r.status_code if "r" in locals() else None},
        "paper_trade": True,
        "execution_allowed": False,
    }


register(ToolSpec("aura_agents_list", aura_agents_list, _v0, risk="low", mutating=False,
                  summary="Lista agentes AURA no Engine (só leitura)"))


def aura_agents_activate(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "agentes NÃO activados. AUTORIZO para gravar marcadores paper-only."}
    out = {"ok": True, "execution_allowed": False}
    try:
        r = requests.post(MATRIZ + "/api/aura/tools/activate-all", json={}, timeout=12)
        out["matriz_activate"] = {"status": r.status_code, "body": (r.json() if r.content else {})}
    except Exception as e:  # noqa: BLE001
        out["matriz_activate"] = {"error": str(e)[:160]}
    try:
        scripts = str(paths.PROJECT_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import aura_chat_agents as ag
        out["operator"] = str(ag.activate_analysis_agents())[:600]
    except Exception as e:  # noqa: BLE001
        out["operator"] = str(e)[:160]
    return out


register(ToolSpec("aura_agents_activate", aura_agents_activate, _v0, risk="medium", mutating=True,
                  summary="Activa agentes de análise paper-only (sem apostas reais)"))


def _v_restart(args) -> dict:
    name = str((args or {}).get("service") or "engine").strip().lower()
    if name == "voz":
        name = "voice"
    if name in ("tudo", "todos", "all", "sistema", "aura"):
        name = "core"
    if name not in RESTARTABLE:
        raise ValidationError("serviço deve ser engine|bridge|matriz|voice|core")
    return {"service": name}


def aura_restart(args, ctx) -> dict:
    a = _v_restart(args)
    if ctx.dry():
        return {"dry_run": True, "would_restart": a["service"],
                "nota": "Hermes e Ollama não são mortos."}
    scripts = str(paths.PROJECT_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import aura_chat_agents as ag
    text = ag.restart_service(a["service"])
    return {"ok": True, "service": a["service"], "result": str(text)[:800],
            "execution_allowed": False}


register(ToolSpec("aura_restart", aura_restart, _v_restart, risk="high", mutating=True,
                  summary="Reinicia engine|bridge|matriz|voice|core. Nunca mata Ollama/Hermes."))
