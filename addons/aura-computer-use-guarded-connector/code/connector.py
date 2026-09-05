"""Conector isolado — todas as ações de CU bloqueadas até segunda implantação."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

try:
    from .policy import GuardedPolicy, load_manifest
except ImportError:  # script/path load
    from policy import GuardedPolicy, load_manifest  # type: ignore


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    blocked: bool
    reason: str
    executed: bool = False
    computer_use_enabled: bool = False
    network_used: bool = False


class GuardedComputerUseConnector:
    """Stub de governança. Não controla mouse/teclado/navegador."""

    SENSITIVE = frozenset(
        {
            "email", "bank", "wallet", "exchange", "betting", "payment",
            "social", "password", "cookie", "authenticated", "yolo", "unrestricted",
        }
    )

    def __init__(self, policy: GuardedPolicy | None = None) -> None:
        self.policy = policy or GuardedPolicy.from_manifest()
        self.policy.assert_inert()
        self.manifest = load_manifest()

    def status(self) -> dict[str, Any]:
        return {
            "addon": "aura-computer-use-guarded-connector",
            "computer_use_enabled": self.policy.computer_use_enabled,
            "execution_allowed": self.policy.execution_allowed,
            "approval_required": self.policy.approval_required,
            "network_allowed": self.policy.network_allowed,
            "driver_external_installed": bool(self.manifest.get("driver_external_installed")),
            "services_started": list(self.manifest.get("services_started") or []),
        }

    def request_action(self, action: str, target: str = "", meta: Mapping[str, Any] | None = None) -> ActionResult:
        blob = f"{action} {target} {meta or {}}".lower()
        for s in self.SENSITIVE:
            if s in blob:
                return ActionResult(
                    ok=False,
                    blocked=True,
                    reason=f"blocked_sensitive:{s}",
                    executed=False,
                )
        if not self.policy.computer_use_enabled:
            return ActionResult(
                ok=False,
                blocked=True,
                reason="computer_use_disabled_install_stage",
                executed=False,
            )
        if not self.policy.execution_allowed:
            return ActionResult(
                ok=False,
                blocked=True,
                reason="execution_not_allowed",
                executed=False,
            )
        return ActionResult(ok=False, blocked=True, reason="fail_closed", executed=False)
