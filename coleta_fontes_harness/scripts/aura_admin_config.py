#!/usr/bin/env python3
"""Validated configuration contracts for the AURA administrator runtime."""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from .aura_admin_core import AutonomyMode, CANONICAL_DB_PATH
except ImportError:
    from aura_admin_core import AutonomyMode, CANONICAL_DB_PATH


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PlannerConfig:
    timeout_s: float = 30.0
    max_steps: int = 32
    max_context_chars: int = 32_000


@dataclass(frozen=True)
class BreakerConfig:
    failure_threshold: int = 3
    cooldown_s: float = 30.0


@dataclass(frozen=True)
class RuntimeConfig:
    schema_version: int = 1
    mode: AutonomyMode = AutonomyMode.PLAN_ONLY
    paper_trade_only: bool = True
    risk_threshold: float = 70.0
    database_path: str = str(CANONICAL_DB_PATH)
    embedding_model: str = "configured"
    planner: PlannerConfig = PlannerConfig()
    breaker: BreakerConfig = BreakerConfig()

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mode"] = self.mode.value
        return result


_FORBIDDEN_KEYS = re.compile(r"(secret|token|password|api[_-]?key|private[_-]?key|credential)", re.I)
_ALLOWED_TOP_LEVEL = {"schema_version", "mode", "paper_trade_only", "risk_threshold", "database_path", "embedding_model", "planner", "breaker"}
_ALLOWED_MODES = {item.value for item in AutonomyMode}


def _number(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise ConfigError(f"{name} must be between {minimum} and {maximum}") from None
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return numeric


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return int(value)


def load_config(document: Mapping[str, Any] | str | Path) -> RuntimeConfig:
    if isinstance(document, Path):
        try:
            document = document.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"cannot read config: {type(exc).__name__}") from exc
    if isinstance(document, str):
        try:
            document = json.loads(document)
        except json.JSONDecodeError as exc:
            raise ConfigError("config must be valid JSON") from exc
    if not isinstance(document, Mapping):
        raise ConfigError("config root must be an object")
    unknown = [key for key in document if key not in _ALLOWED_TOP_LEVEL]
    if unknown:
        raise ConfigError(f"unknown config fields: {sorted(unknown, key=repr)}")
    schema_version = document.get("schema_version", 1)
    if schema_version != 1:
        raise ConfigError("unsupported config schema_version")
    try:
        mode = AutonomyMode(document.get("mode", AutonomyMode.PLAN_ONLY.value))
    except (TypeError, ValueError) as exc:
        raise ConfigError("invalid autonomy mode") from exc
    if document.get("paper_trade_only", True) is not True:
        raise ConfigError("paper_trade_only must remain true")
    risk_threshold = _number(document.get("risk_threshold", 70.0), name="risk_threshold", minimum=1.0, maximum=100.0)
    database_path = document.get("database_path", str(CANONICAL_DB_PATH))
    if not isinstance(database_path, str) or not database_path or Path(database_path).is_absolute() or Path(database_path).as_posix() != CANONICAL_DB_PATH.as_posix():
        raise ConfigError("database_path must be exactly the relative canonical path engine/aura_quant_x.db")
    embedding_model = document.get("embedding_model", "configured")
    if not isinstance(embedding_model, str) or not embedding_model.strip() or _FORBIDDEN_KEYS.search(embedding_model):
        raise ConfigError("embedding_model must be a safe non-empty identifier")
    planner_raw = document.get("planner", {})
    breaker_raw = document.get("breaker", {})
    if not isinstance(planner_raw, Mapping) or not isinstance(breaker_raw, Mapping):
        raise ConfigError("planner and breaker must be objects")
    if set(planner_raw) - {"timeout_s", "max_steps", "max_context_chars"}:
        raise ConfigError("unknown planner configuration field")
    if set(breaker_raw) - {"failure_threshold", "cooldown_s"}:
        raise ConfigError("unknown breaker configuration field")
    planner = PlannerConfig(
        timeout_s=_number(planner_raw.get("timeout_s", 30.0), name="planner.timeout_s", minimum=0.1, maximum=300.0),
        max_steps=_integer(planner_raw.get("max_steps", 32), name="planner.max_steps", minimum=1, maximum=32),
        max_context_chars=_integer(planner_raw.get("max_context_chars", 32_000), name="planner.max_context_chars", minimum=1_000, maximum=128_000),
    )
    breaker = BreakerConfig(
        failure_threshold=_integer(breaker_raw.get("failure_threshold", 3), name="breaker.failure_threshold", minimum=1, maximum=20),
        cooldown_s=_number(breaker_raw.get("cooldown_s", 30.0), name="breaker.cooldown_s", minimum=1.0, maximum=3_600.0),
    )
    return RuntimeConfig(schema_version=1, mode=mode, paper_trade_only=True, risk_threshold=risk_threshold, database_path=database_path, embedding_model=embedding_model.strip(), planner=planner, breaker=breaker)


__all__ = ["BreakerConfig", "ConfigError", "PlannerConfig", "RuntimeConfig", "load_config"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        config = load_config(args.path)
    except ConfigError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "config": config.public_dict()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
