"""Política de runtime AURA — paper por padrão, LIVE só com opt-in explícito.

Variáveis de ambiente (todas devem estar alinhadas para liberar LIVE):
  AURA_PAPER_TRADE=0|1          (default 1)
  AURA_EXECUTION_ALLOWED=0|1   (default 0)
  AURA_UNLOCK_LIVE=1           (default 0) — chave mestra
  AURA_UNLOCK_CONFIRM=I_ACCEPT_REAL_EXECUTION_RISK

Arquivo opcional de confirmação (Windows):
  config/UNLOCK_LIVE.flag  com a mesma frase I_ACCEPT_REAL_EXECUTION_RISK

Sem as três condições + frase de confirmação, o sistema permanece PAPER.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

_CONFIRM_PHRASE = "I_ACCEPT_REAL_EXECUTION_RISK"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "live"}


def _confirm_file_ok() -> bool:
    candidates = [
        Path("config/UNLOCK_LIVE.flag"),
        Path(__file__).resolve().parents[2] / "config" / "UNLOCK_LIVE.flag",
        Path.cwd() / "config" / "UNLOCK_LIVE.flag",
    ]
    for path in candidates:
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if _CONFIRM_PHRASE in text:
                    return True
        except OSError:
            continue
    return False


def is_unlock_requested() -> bool:
    master = _env_bool("AURA_UNLOCK_LIVE", False)
    env_confirm = (os.environ.get("AURA_UNLOCK_CONFIRM") or "").strip() == _CONFIRM_PHRASE
    return master and (env_confirm or _confirm_file_ok())


def get_system_policy() -> Dict[str, Any]:
    """Política efetiva. Pacote V37.3.53 é paper-only: LIVE nunca é concedido.

    Flags de unlock são registadas em unlock_requested para diagnóstico.
    LIVE exige pacote futuro + confirmação humana explícita, não um env solto.
    """
    return {
        "paper_trade": True,
        "execution_allowed": False,
        "glm_advisory_only": True,
        "glm_enabled": False,
        "hermes_primary": True,
        "skill_execution": _env_bool("AURA_E_ENABLE_SKILL_EXECUTION", True),
        "mode": "paper",
        "unlock_active": False,
        "unlock_requested": is_unlock_requested(),
    }


def assert_safety_invariants() -> None:
    """Mantém fail-closed se unlock incompleto. Em LIVE validado, não bloqueia."""
    policy = get_system_policy()
    if policy["unlock_active"] and policy["mode"] == "live":
        return
    if policy["paper_trade"] is not True:
        raise RuntimeError("PAPER_TRADE_MUST_BE_TRUE_WITHOUT_FULL_UNLOCK")
    if policy["execution_allowed"] is not False:
        raise RuntimeError("REAL_EXECUTION_FORBIDDEN_WITHOUT_FULL_UNLOCK")


__all__ = [
    "get_system_policy",
    "assert_safety_invariants",
    "is_unlock_requested",
]


class SafeHotReloader:
    """Recarrega thresholds sem permitir alterações de modo ou execução."""
    _FORBIDDEN = frozenset({
        "paper_trade", "execution_allowed", "unlock_active", "mode",
        "AURA_PAPER_TRADE", "AURA_EXECUTION_ALLOWED", "AURA_UNLOCK_LIVE",
    })

    def __init__(self, config_path: str = "agents/glm_config.yaml") -> None:
        import threading
        self.config_path = Path(config_path)
        self._lock = threading.RLock()
        self._config: Dict[str, Any] = {}
        self._last_mtime_ns = -1
        self.reload()

    def reload(self) -> Dict[str, Any]:
        if not self.config_path.is_file():
            return self.snapshot()
        try:
            import yaml
            stat = self.config_path.stat()
            if stat.st_mtime_ns == self._last_mtime_ns:
                return self.snapshot()
            candidate = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            if not isinstance(candidate, dict):
                raise ValueError("configuração deve ser um objeto")
            if any(str(key) in self._FORBIDDEN for key in candidate):
                raise ValueError("configuração tenta alterar invariantes de segurança")
            with self._lock:
                self._config = dict(candidate)
                self._last_mtime_ns = stat.st_mtime_ns
        except Exception:
            return self.snapshot()
        return self.snapshot()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._config.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._config)


HOT_CONFIG = SafeHotReloader()
