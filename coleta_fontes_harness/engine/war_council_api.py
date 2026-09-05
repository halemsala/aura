"""HTTP advisory do Conselho de Guerra. Sem execução real."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engine.agents.war_council import convene, record_result

router = APIRouter(prefix="/api/council", tags=["war-council"])


class CouncilBody(BaseModel):
    features: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)


class ForensicsBody(BaseModel):
    trade: dict[str, Any] = Field(default_factory=dict)
    result: str = "LOSS"


@router.get("/status")
def api_status() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": True,
        "paper_trade": True,
        "execution_allowed": False,
        "modules": ["red_team", "forensics", "elo", "local_council", "crew_fallback"],
    }


@router.post("/convene")
def api_convene(body: CouncilBody) -> dict[str, Any]:
    return convene(body.features, body.decision)


@router.get("/elo")
def api_elo(home: str, away: str, odd: float = 0.0) -> dict[str, Any]:
    from engine.agents_glm.elo_rating_agent import ELO_AGENT

    return ELO_AGENT.inspect(home, away, odd)


@router.post("/forensics")
def api_forensics(body: ForensicsBody) -> dict[str, Any]:
    return record_result(body.trade, body.result)
