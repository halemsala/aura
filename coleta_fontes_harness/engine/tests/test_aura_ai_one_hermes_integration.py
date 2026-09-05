from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from engine.agents.aura_hermes_router import route_corner_analysis
from engine.agents.llm_firewall import FirewallStatus, parse_advisory_output
from engine.aura_ai_one.adapter import AuraAIOneAdapter, HermesAuditAdapter
from engine.aura_ai_one.contracts import AuraAIOneProposal
from engine.aura_ai_one.features import build_temporal_features
from engine.core.runtime_manifest import RuntimeManifest
from engine.aura_controller import AuraController


def sample_points() -> list[dict]:
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    return [
        {
            "timestamp": (base + timedelta(minutes=0)).isoformat(),
            "minute": 10,
            "fixture_id": "fix-001",
            "corners_home": 1,
            "corners_away": 0,
            "attacks_home": 20,
            "attacks_away": 12,
            "dangerous_home": 7,
            "dangerous_away": 4,
        },
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "minute": 20,
            "fixture_id": "fix-001",
            "corners_home": 3,
            "corners_away": 1,
            "attacks_home": 30,
            "attacks_away": 18,
            "dangerous_home": 12,
            "dangerous_away": 8,
        },
    ]


def test_temporal_features_are_deterministic_and_local() -> None:
    features = build_temporal_features(sample_points(), now=datetime.now(timezone.utc))
    assert features.fixture_id == "fix-001"
    assert features.corner_delta_10m == 3
    assert features.attack_delta_10m == 16
    assert features.dangerous_delta_10m == 9
    assert features.paper_trade is True
    assert features.execution_allowed is False


def test_runtime_manifest_cannot_be_constructed_with_real_execution() -> None:
    manifest = RuntimeManifest()
    assert manifest.paper_trade is True
    assert manifest.execution_allowed is False
    with pytest.raises(ValidationError):
        RuntimeManifest(execution_allowed=True)


def test_aura_ai_one_default_adapter_is_advisory_only() -> None:
    features = build_temporal_features(sample_points())
    proposal = AuraAIOneAdapter().propose(features)
    assert isinstance(proposal, AuraAIOneProposal)
    assert proposal.paper_trade is True
    assert proposal.execution_allowed is False
    assert proposal.approved is False
    assert proposal.stake_pct == 0.0
    assert proposal.exposure == 0.0
    assert proposal.evidence


def test_hermes_cannot_increase_confidence_without_new_evidence() -> None:
    features = build_temporal_features(sample_points())
    proposal = AuraAIOneAdapter().propose(features)
    review = HermesAuditAdapter().review(proposal, features)
    assert review.confidence <= proposal.confidence
    assert review.paper_trade is True
    assert review.execution_allowed is False
    assert review.approved is False


def test_router_returns_aura_hermes_envelope_in_fixed_order() -> None:
    envelope = route_corner_analysis(sample_points(), fixture_id="fix-001")
    assert envelope.contract_version == "aura-hermes-advisory-v1"
    assert envelope.order == ("AURA_AI_ONE_QUANT", "HERMES_AUDIT")
    assert envelope.proposal is not None
    assert envelope.review is not None
    assert envelope.final_decision in {"ENTRA", "AGUARDA", "NAO_ENTRA", "BLOCK"}
    assert envelope.execution_allowed is False


def test_router_blocks_stale_evidence() -> None:
    stale = sample_points()
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    for point in stale:
        point["timestamp"] = old.isoformat()
    envelope = route_corner_analysis(stale, fixture_id="fix-001")
    assert envelope.final_decision in {"AGUARDA", "BLOCK"}
    assert envelope.review.status in {"DOWNGRADE", "BLOCK"}


def test_firewall_blocks_invalid_json_and_extra_fields() -> None:
    invalid = parse_advisory_output("not-json")
    assert invalid.status is FirewallStatus.BLOCK
    extra = parse_advisory_output(
        '{"decision":"AGUARDA","confidence":0.2,"paper_trade":true,"execution_allowed":false,"unexpected":1}'
    )
    assert extra.status is FirewallStatus.BLOCK


def test_controller_records_only_redacted_advisory_event() -> None:
    class RecordingLedger:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def append_event(self, event_type: str, payload: dict, **kwargs) -> None:
            self.events.append({"event_type": event_type, "payload": payload, **kwargs})

    ledger = RecordingLedger()
    result = AuraController(ledger=ledger).evaluate_corners(sample_points())
    assert result.execution_allowed is False
    assert result.approved is False
    assert len(ledger.events) == 1
    assert "raw_payload" not in ledger.events[0]["payload"]
