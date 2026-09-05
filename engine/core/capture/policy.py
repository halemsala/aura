from __future__ import annotations

try:
    from engine.core.policy_runtime import assert_safety_invariants, get_system_policy
except Exception:
    try:
        from core.policy_runtime import assert_safety_invariants, get_system_policy
    except Exception:
        def get_system_policy():
            return {
                "paper_trade": True,
                "execution_allowed": False,
                "glm_advisory_only": True,
                "glm_enabled": False,
                "hermes_primary": True,
                "skill_execution": True,
                "mode": "paper",
                "unlock_active": False,
            }

        def assert_safety_invariants():
            p = get_system_policy()
            if p.get("paper_trade") is not True and not p.get("unlock_active"):
                raise RuntimeError("PAPER_TRADE_MUST_BE_TRUE_WITHOUT_FULL_UNLOCK")
            if p.get("execution_allowed") is not False and not p.get("unlock_active"):
                raise RuntimeError("REAL_EXECUTION_FORBIDDEN_WITHOUT_FULL_UNLOCK")

SYSTEM_POLICY = get_system_policy()

__all__ = ["SYSTEM_POLICY", "assert_safety_invariants"]
