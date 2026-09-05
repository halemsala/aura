"""Validador/reparador local de JSON advisory do LLM."""
from __future__ import annotations

import json
from typing import Any, Dict


class LLMOutputHealer:
    REQUIRED = ("decision", "confidence", "score", "reasoning", "triggers", "kills")

    def heal(self, raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("output_not_object")
        except (ValueError, TypeError, json.JSONDecodeError):
            return {"decision": "AGUARDA", "confidence": 0.0, "score": 0,
                    "reasoning": "invalid_llm_json", "triggers": [], "kills": ["LLM_JSON_INVALID"],
                    "paper_trade": True, "execution_allowed": False}
        result = dict(value)
        result.setdefault("decision", "AGUARDA")
        result.setdefault("confidence", 0.0)
        result.setdefault("score", 0)
        result.setdefault("reasoning", "")
        result.setdefault("triggers", [])
        result.setdefault("kills", [])
        result["paper_trade"] = True
        result["execution_allowed"] = False
        return result


OUTPUT_HEALER = LLMOutputHealer()
__all__ = ["LLMOutputHealer", "OUTPUT_HEALER"]
