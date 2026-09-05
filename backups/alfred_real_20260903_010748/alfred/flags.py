"""Flags persistidas. paper_trade ≠ execução de apostas.
execution_allowed continua sempre false neste módulo.
system_repair_allowed é o que permite correcções reais ao código do Aura."""
import json
import time
from pathlib import Path

from . import paths

FLAGS_PATH = paths.PROJECT_ROOT / "config" / "aura_flags.json"
AUDIT = paths.DATA_ROOT / "flags_audit.jsonl"

DEFAULTS = {
    "paper_trade": True,
    "execution_allowed": False,
    "system_repair_allowed": False,
    "voice_enabled": False,
    "observe_pc_enabled": True,
}


def load_flags() -> dict:
    data = dict(DEFAULTS)
    if FLAGS_PATH.exists():
        try:
            data.update(json.loads(FLAGS_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    data["execution_allowed"] = False  # nunca ligar apostas reais por este ficheiro
    if not FLAGS_PATH.exists():
        save_flags(data, reason="criação inicial")
    return data


def save_flags(data: dict, reason: str = "") -> dict:
    data = dict(data)
    data["execution_allowed"] = False
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["reason"] = (reason or "")[:300]
    FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FLAGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "flags": data}, ensure_ascii=False) + "\n")
    return data


def paper_trade_authorized_off() -> bool:
    return load_flags().get("paper_trade") is False
