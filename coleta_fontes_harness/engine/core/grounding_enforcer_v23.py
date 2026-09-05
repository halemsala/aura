# engine/core/grounding_enforcer_v23.py — fail-closed parse of GLM advisory output
from __future__ import annotations
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field, field_validator
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore
    Field = lambda *a, **k: None  # type: ignore
    field_validator = lambda *a, **k: (lambda f: f)  # type: ignore


class GroundedPrediction(BaseModel):
    action: str = Field(..., description="CORNER_KICK or NO_ACTION")
    probability_pct: float = Field(..., ge=0.0, le=100.0)
    confidence_bucket: str = Field(..., description="LOW|MEDIUM|HIGH")
    mathematical_basis: str = Field(..., description="short basis string")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("CORNER_KICK", "NO_ACTION"):
            raise ValueError(f"Ação inválida: {v}")
        return v


COLD_SYSTEM_PROMPT = """
REGRA OPERACIONAL ESTRITA (NÃO VIOLAR):
1. Você é um motor de cálculo probabilístico. Não tenha opiniões.
2. O ambiente é PAPER_TRADE. Proibido sugerir dinheiro real, stakes ou apostas.
3. Saída OBRIGATÓRIA em JSON válido matching o schema fornecido.
4. Se dados insuficientes: {"action":"NO_ACTION","probability_pct":0.0,"confidence_bucket":"LOW","mathematical_basis":"INSUFFICIENT_DATA"}.
5. Não use markdown, não use explicações fora do JSON.
6. paper_trade=true. execution_allowed=false. GLM_ADVISORY_ONLY.
"""


def enforce_grounding(raw_llm_output: str) -> dict[str, Any]:
    """Parse + validate. Fail-closed on hallucination of format."""
    text = str(raw_llm_output or "")
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= 0:
            raise ValueError("no_json")
        clean = text[start:end]
        try:
            pred = GroundedPrediction.model_validate_json(clean)  # pydantic v2
        except Exception:
            pred = GroundedPrediction.parse_raw(clean)  # type: ignore  # v1
        return pred.model_dump() if hasattr(pred, "model_dump") else pred.dict()  # type: ignore
    except Exception as e:
        return {
            "action": "NO_ACTION",
            "probability_pct": 0.0,
            "confidence_bucket": "LOW",
            "mathematical_basis": f"GROUNDING_PARSE_FAIL:{str(e)[:50]}",
            "paper_trade": True,
            "execution_allowed": False,
        }
