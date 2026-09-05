import json, os
from . import paths

DEFAULTS = {
    "model": "qwen3:8b",
    "ollama_url": "http://127.0.0.1:11434",
    "host": "127.0.0.1",
    "port": 8791,
    "num_ctx": 3072,
    "num_predict": 1024,
    "temperature": 0.3,
    "keep_alive": "-1",
    "no_browser_polling": True,
    "paper_trade": True,
    "execution_allowed": False,
    "require_confirmation_for_sensitive_tools": True,
    "max_tasks": 12,
    "max_retries": 2,
    "task_timeout_s": 90,
    "llm_timeout_s": 120,
    "request_cooldown_s": 8,
    "capture_retention_hours": 24,
    "allowed_roots": ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"],
    "gpu_share_max_pct": 60,
    "gpu_share_port": 8795,
    "services": {
        "ollama": {"type": "http", "url": "http://127.0.0.1:11434/api/tags"},
        "alfred": {"type": "tcp", "port": 8791},
        "hermes": {"type": "tcp", "port": 8777},
        "engine": {"type": "http", "url": "http://127.0.0.1:8765/api/health"},
        "bridge": {"type": "http", "url": "http://127.0.0.1:8080/health"},
        "matriz": {"type": "http", "url": "http://127.0.0.1:8766/health"},
        "voice": {"type": "http", "url": "http://127.0.0.1:8099/api/voice/health"},
    },
    "vision_model": ""
}

_cache = None

def get_config() -> dict:
    global _cache
    if _cache is None:
        cfg = dict(DEFAULTS)
        if paths.CONFIG_PATH.exists():
            try:
                cfg.update(json.loads(paths.CONFIG_PATH.read_text(encoding="utf-8")))
            except Exception as e:
                raise RuntimeError(f"config/alfred.json inválido: {e}") from e
        # overrides por ambiente (usados pelos testes; nunca alteram o ficheiro)
        if os.environ.get("ALFRED_VISION_MODEL"):
            cfg["vision_model"] = os.environ["ALFRED_VISION_MODEL"]
        if os.environ.get("ALFRED_EXEC_ALLOWED") == "1":
            cfg["execution_allowed"] = True
        if os.environ.get("ALFRED_PAPER_TRADE") == "0":
            cfg["paper_trade"] = False
        try:
            from .flags import load_flags
            fl = load_flags()
            cfg["paper_trade"] = bool(fl.get("paper_trade", cfg.get("paper_trade")))
            cfg["system_repair_allowed"] = bool(fl.get("system_repair_allowed"))
            cfg["execution_allowed"] = False
        except Exception:  # noqa: BLE001
            pass
        _cache = cfg
    return _cache

def reset_config_cache():
    global _cache
    _cache = None
