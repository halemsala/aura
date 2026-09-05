"""Catálogo de conectores inerte: valida pedidos, mas nunca acessa a rede."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import ConnectorRequest


@dataclass(frozen=True)
class ConnectorSpec:
    name: str
    operations: frozenset[str]
    description: str


class ReadOnlyConnectorCatalog:
    """Allowlist de capacidades; o host deve injetar adapters aprovados."""

    def __init__(self, specs: tuple[ConnectorSpec, ...] | None = None) -> None:
        self._specs = {s.name: s for s in (specs or default_specs())}

    def capabilities(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"connector": s.name, "operations": tuple(sorted(s.operations)), "mode": "read-only"}
            for s in sorted(self._specs.values(), key=lambda x: x.name)
        )

    def validate(self, request: ConnectorRequest) -> None:
        spec = self._specs.get(request.connector)
        if spec is None or request.operation not in spec.operations:
            raise PermissionError("connector operation is not allowlisted")
        if any(k.lower() in {"token", "secret", "password", "authorization"} for k in request.arguments):
            raise PermissionError("credentials are not accepted in connector arguments")

    def plan(self, request: ConnectorRequest) -> dict[str, Any]:
        self.validate(request)
        return {
            "status": "PLANNED",
            "connector": request.connector,
            "operation": request.operation,
            "arguments_keys": tuple(sorted(str(k) for k in request.arguments)),
            "timeout_seconds": request.timeout_seconds,
            "execution_allowed": False,
        }


def default_specs() -> tuple[ConnectorSpec, ...]:
    return (
        ConnectorSpec("documents", frozenset({"search", "read"}), "Documentos aprovados"),
        ConnectorSpec("tickets", frozenset({"search", "read"}), "Tickets e incidentes"),
        ConnectorSpec("calendar", frozenset({"search", "read"}), "Agenda"),
        ConnectorSpec("metrics", frozenset({"query"}), "Métricas pré-definidas"),
        ConnectorSpec("aura_state", frozenset({"health", "status", "capabilities"}), "Estado do AURA"),
    )


def unavailable_executor(*_: Any, **__: Any) -> None:
    raise RuntimeError("No executor is bundled; host integration is an explicit opt-in step")
