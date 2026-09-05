"""Motor de Contexto e Sandbox Virtual: simula ferramentas de forma inerte."""
from __future__ import annotations

import time
from typing import Any, Callable, Mapping

from .contracts import DryRunAction


class VirtualSandbox:
    """
    Ferramentas virtuais apenas. executed=False sempre.
    Nenhuma ferramenta real é tocada.
    """

    def __init__(self) -> None:
        self._registry: dict[str, Callable[[Mapping[str, Any]], Any]] = {
            "math.calculate_stake": self._mock_stake,
            "data.get_odds": self._mock_odds,
            "system.health_check": self._mock_health,
        }

    def execute(self, action: DryRunAction) -> dict[str, Any]:
        tool = self._registry.get(action.action)
        if not tool:
            return {
                "tool": action.action,
                "executed": False,
                "status": "ERROR",
                "reason": "Tool not allowed in sandbox",
                "timestamp": time.time(),
            }
        result = tool(dict(action.parameters))
        return {
            "tool": action.action,
            "executed": False,  # invariante
            "simulated_result": result,
            "timestamp": time.time(),
            "paper_trade": True,
            "execution_allowed": False,
        }

    def _mock_stake(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {"simulated_stake": 0.0, "currency": "PAPER", "params_seen": dict(params)}

    def _mock_odds(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {"mocked_odds": 1.85, "source": "virtual_sandbox", "params_seen": dict(params)}

    def _mock_health(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {"status": "OK", "paper_trade": True, "execution_allowed": False}


class ContextEngine:
    """Acúmulo de evidências durante ciclos do Ralph Loop (memória de curto prazo)."""

    def __init__(self) -> None:
        self._memory: list[dict[str, Any]] = []

    def add(self, cycle: int, source: str, data: dict[str, Any]) -> None:
        self._memory.append({"cycle": cycle, "source": source, "data": data})

    def clear(self) -> None:
        self._memory.clear()

    def get_context_string(self) -> str:
        if not self._memory:
            return "No prior context."
        lines = []
        for m in self._memory[-32:]:
            lines.append(f"[Cycle {m['cycle']}] {m['source']}: {str(m['data'])[:200]}")
        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._memory)
