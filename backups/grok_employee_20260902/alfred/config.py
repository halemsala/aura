import json, os
from . import paths

DEFAULTS = {
    "model": "qwen3:8b",
    "ollama_url": "http://127.0.0.1:11434",
    "host": "127.0.0.1",
    "port": 8791,
    "num_ctx": 2048,
    "num_predict": 768,
    "temperature": 0.2,
    "keep_alive": "20m",
    "no_browser_polling": True,
    "paper_trade": True,
    "execution_allowed": False,
    "require_confirmation_for_sensitive_tools": True,
    "max_tasks": 8,
    "max_retries": 2,
    "task_timeout_s": 30,
    "llm_timeout_s": 90,
    "request_cooldown_s": 60,
    "capture_retention_hours": 24,
    "allowed_roots": ["Desktop", "Documents", "Downloads"],
    "services": {
        "ollama": {"type": "http", "url": "http://127.0.0.1:11434/api/tags"},
        "alfred": {"type": "tcp", "port": 8791},
        "hermes": {"type": "tcp", "port": 8777}
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
        _cache = cfg
    return _cache

def reset_config_cache():
    global _cache
    _cache = None
