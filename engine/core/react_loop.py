# engine/core/react_loop.py — V23 ReAct controlado e fail-closed
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(slots=True)
class ReActState:
    attempt: int = 0
    observations: list[Any] = field(default_factory=list)
    last_error: str = ""


def fail_closed_advisory(state: ReActState) -> dict[str, Any]:
    return {
        "ok": False,
        "fail_closed": True,
        "attempts": state.attempt,
        "last_error": state.last_error,
        "paper_trade": True,
        "execution_allowed": False,
        "advisory_only": True,
    }


def react_loop(
    observe: Callable[[], Any],
    propose: Callable[[Any], Any],
    validate: Callable[[Any], bool],
    fallback: Callable[[str], Optional[Any]],
    cleanup: Optional[Callable[[], Any]] = None,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """observe -> plan -> validate read-only -> advisory | cleanup+fallback -> fail_closed."""
    state = ReActState()
    for state.attempt in range(1, max_attempts + 1):
        try:
            observation = observe()
            state.observations.append(observation)
            plan = propose(observation)
            if validate(plan):
                return {
                    "ok": True,
                    "advisory": plan,
                    "attempts": state.attempt,
                    "paper_trade": True,
                    "execution_allowed": False,
                }
            state.last_error = "validation_failed"
        except Exception as exc:
            state.last_error = str(exc)
        if cleanup:
            try:
                cleanup()
            except Exception:
                pass
        route = fallback(state.last_error) if fallback else None
        if route is None:
            break
    return fail_closed_advisory(state)
