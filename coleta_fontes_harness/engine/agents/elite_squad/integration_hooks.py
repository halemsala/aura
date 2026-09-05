"""Optional hooks for Engine/Bridge — call explicitly; not auto-imported by server.

Usage (advisory):
    from engine.agents.elite_squad.integration_hooks import audit_proposal, sanitize_feed
"""
from __future__ import annotations

from typing import Any

from .elite_squad_advisory_stubs import DATA_JANITOR, RED_TEAM, FORENSICS, ROI_AUDITOR


def sanitize_feed(raw: dict[str, Any]) -> dict[str, Any]:
    return DATA_JANITOR.sanitize_feed(raw)


def audit_proposal(features: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    """If proposal is ENTRA and RedTeam vetoes → effective_decision AGUARDA."""
    proposal = dict(proposal)
    proposal.setdefault("paper_trade", True)
    proposal.setdefault("execution_allowed", False)
    proposal["paper_trade"] = True
    proposal["execution_allowed"] = False
    out = RED_TEAM.audit_decision(features, proposal)
    try:
        from pathlib import Path
        import json, time, os
        root = Path(os.environ.get("AURA_ROOT", r"C:\aura"))
        if not (root / "engine").exists():
            root = Path(__file__).resolve().parents[3]
        path = root / "data" / "elite_squad" / "last_veto.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(out)
        payload["at"] = time.time()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return out


def record_paper_result(trade_data: dict[str, Any], result: str) -> dict[str, Any]:
    return FORENSICS.execute_autopsy(trade_data, result)


def paper_roi_stats(days: int = 1) -> dict[str, Any]:
    return ROI_AUDITOR.get_daily_stats(days=days)
