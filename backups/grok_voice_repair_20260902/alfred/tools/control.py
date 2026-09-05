"""Ferramentas de controlo do sistema Aura (allowlist, só localhost)."""
import json
from pathlib import Path

from .. import paths
from ..config import get_config
from ..registry import ToolSpec, register
from ..validators import ValidationError
from . import system_tools

SECRET_KEYS = ("key", "token", "secret", "password", "passwd", "api_key")


def _v0(args) -> dict:
    return {}


def gpu_report(args, ctx) -> dict:
    st = system_tools.system_status({}, ctx)
    return {"gpu": st.get("gpu"), "ollama": st.get("ollama"),
            "ram_used_pct": st.get("ram_used_pct"), "cpu_percent": st.get("cpu_percent")}


register(ToolSpec("gpu_report", gpu_report, _v0, risk="low", mutating=False,
                  summary="VRAM/GPU/CPU/RAM e estado Ollama (só leitura)"))


def services_status(args, ctx) -> dict:
    out = {}
    for name in sorted(get_config().get("services") or {}):
        try:
            out[name] = system_tools.check_service({"service": name}, ctx)
        except Exception as e:  # noqa: BLE001
            out[name] = {"online": False, "error": str(e)[:150]}
    cfg = get_config()
    out["flags"] = {"paper_trade": cfg.get("paper_trade"),
                    "execution_allowed": cfg.get("execution_allowed"),
                    "model": cfg.get("model")}
    return out


register(ToolSpec("services_status", services_status, _v0, risk="low", mutating=False,
                  summary="Health Ollama/Alfred/Hermes e flags paper_trade/execution_allowed"))


def runtime_flags(args, ctx) -> dict:
    cfg = get_config()
    return {
        "paper_trade": cfg.get("paper_trade"),
        "execution_allowed": cfg.get("execution_allowed"),
        "model": cfg.get("model"),
        "host": cfg.get("host"),
        "port": cfg.get("port"),
        "num_ctx": cfg.get("num_ctx"),
        "keep_alive": cfg.get("keep_alive"),
        "no_browser_polling": cfg.get("no_browser_polling"),
        "nota": "estas flags não são alteráveis por ferramentas",
    }


register(ToolSpec("runtime_flags", runtime_flags, _v0, risk="low", mutating=False,
                  summary="Lê flags de segurança (não permite alterá-las)"))


def _redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in SECRET_KEYS):
                out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def read_alfred_config(args, ctx) -> dict:
    p = paths.CONFIG_PATH
    if not p.is_file():
        raise ValidationError("config/alfred.json ausente")
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"path": str(p), "config": _redact(data)}


register(ToolSpec("read_alfred_config", read_alfred_config, _v0, risk="low", mutating=False,
                  summary="Lê config/alfred.json com segredos redigidos"))


def list_aura_root(args, ctx) -> dict:
    root = paths.PROJECT_ROOT
    items = []
    for p in sorted(root.iterdir()):
        if p.name.startswith("."):
            continue
        try:
            items.append({"name": p.name, "dir": p.is_dir(),
                          "size": (p.stat().st_size if p.is_file() else None)})
        except OSError:
            continue
    return {"root": str(root), "count": len(items), "items": items[:200]}


register(ToolSpec("list_aura_root", list_aura_root, _v0, risk="low", mutating=False,
                  summary="Lista a raiz C:\\aura (só nomes, sem venv)"))


def _v_log_list(args) -> dict:
    return {"lines": max(1, min(int((args or {}).get("lines") or 20), 80))}


def list_recent_logs(args, ctx) -> dict:
    a = _v_log_list(args)
    roots = [paths.DATA_ROOT, paths.PROJECT_ROOT / "logs_supervisor"]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.log"):
            try:
                if p.stat().st_size > 8_000_000:
                    continue
                found.append({"file": str(p.relative_to(paths.PROJECT_ROOT)),
                              "bytes": p.stat().st_size})
            except OSError:
                continue
            if len(found) >= 40:
                break
    return {"logs": found, "nota": "usa read_recent_log para o conteúdo"}


register(ToolSpec("list_recent_logs", list_recent_logs, _v_log_list, risk="low", mutating=False,
                  summary="Inventário de logs em data/alfred e logs_supervisor"))


def _v_ctrl(args) -> dict:
    args = args or {}
    name = str(args.get("service") or "").strip().casefold()
    action = str(args.get("action") or "status").strip().casefold()
    if name not in ("alfred", "hermes"):
        raise ValidationError("só alfred|hermes (Ollama nunca é parado por esta ferramenta)")
    if action not in ("status", "start", "stop", "restart"):
        raise ValidationError("action deve ser status|start|stop|restart")
    return {"service": name, "action": action}


def control_service(args, ctx) -> dict:
    a = _v_ctrl(args)
    if a["action"] == "status":
        return system_tools.check_service({"service": a["service"]}, ctx)
    if ctx.dry():
        return {"dry_run": True, "service": a["service"], "action": a["action"]}
    if a["action"] in ("stop", "restart") and a["service"] == "hermes":
        return {"blocked": True, "service": "hermes",
                "nota": "parar o Hermes pelo chat derruba o próprio chat. Usa AURA_STOP_ALL.bat / AURA_START_ALL.bat"}
    if a["action"] == "restart" and a["service"] == "alfred":
        return system_tools.restart_service({"service": "alfred"}, ctx)
    if a["action"] == "stop" and a["service"] == "alfred":
        from .. import service as service_mod
        return service_mod.stop_registered()
    if a["action"] == "start" and a["service"] == "alfred":
        from ..boot import _start_alfred
        from ..config import get_config
        _start_alfred(get_config())
        return {"started": True, "service": "alfred"}
    if a["action"] == "start" and a["service"] == "hermes":
        from ..boot import _start_hermes
        _start_hermes()
        return {"started": True, "service": "hermes"}
    raise ValidationError("combinação serviço/acção não suportada")


register(ToolSpec("control_service", control_service, _v_ctrl, risk="high",
                  mutating=True, sensitive=True,
                  summary="status/start/stop/restart de alfred|hermes. Nunca mata Ollama."))
