"""LLM Safe Executor: somente análise/dry-run; execução arbitrária é proibida."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class SandboxResult:
    allowed: bool
    status: str
    reason: str
    details: Dict[str, Any]


class SafeExecSandbox:
    """Valida sintaxe e recusa execução; não usa exec/eval/subprocess."""
    FORBIDDEN = frozenset({"Import", "ImportFrom", "Call", "With", "Try", "Lambda"})

    def inspect(self, source: str) -> SandboxResult:
        text = str(source or "")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return SandboxResult(False, "REJECTED", "syntax_error", {"line": exc.lineno})
        nodes = {type(node).__name__ for node in ast.walk(tree)}
        blocked = sorted(nodes & self.FORBIDDEN)
        if blocked:
            return SandboxResult(False, "REJECTED", "unsafe_ast_nodes", {"nodes": blocked})
        return SandboxResult(False, "DRY_RUN_ONLY", "arbitrary_execution_disabled", {"nodes": sorted(nodes)})

    def execute(self, source: str, context: Dict[str, Any] | None = None) -> SandboxResult:
        return SandboxResult(False, "REJECTED", "execution_disabled_by_policy", {"context_keys": sorted((context or {}).keys())})


SAFE_EXEC = SafeExecSandbox()
__all__ = ["SafeExecSandbox", "SandboxResult", "SAFE_EXEC"]
