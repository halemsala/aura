from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class GroundingEnvelope:
    fixture_id: str
    state_version: int
    freshness_ms: int
    observed: dict
    derived: dict
    missing: list
    confidence: float
    source_hash: str
    def to_dict(self) -> dict:
        return asdict(self)

def build_grounding_envelope(*, fixture_id: str, state_version: int, observed: dict, derived: dict, missing: list, confidence: float, source_hash: str, freshness_ms: int) -> GroundingEnvelope:
    return GroundingEnvelope(str(fixture_id), int(state_version), int(freshness_ms), observed or {}, derived or {}, list(missing or []), float(confidence), str(source_hash))

GROUNDING_PROMPT = "Voce possui somente o Grounding Envelope. OBSERVED=fato, DERIVED=inferencia, MISSING!=0. paper_trade=true. execution_allowed=false."
