"""Conselho de Guerra AURA — paper_trade=true / execution_allowed=false.

Ordem advisory:
  Janitor -> Elo -> Conselho (local sempre; CrewAI se deps+Ollama) -> Red Team -> Forensics
O Red Team tem veto absoluto. Nenhuma etapa autoriza execução real.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Mapping

logger = logging.getLogger("aura.war_council")

PAPER_TRADE = True
EXECUTION_ALLOWED = False
PLAN_ONLY = True


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def features_from_any(source: Any) -> Dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, Mapping):
        data = dict(source)
    else:
        data = {}
        for key in (
            "minute",
            "score",
            "attack_pressure_diff",
            "shots_off_target",
            "corners",
            "corners_home",
            "corners_away",
            "dangerous_delta_10m",
            "attack_delta_10m",
            "corner_delta_10m",
            "home",
            "away",
            "fixture_id",
        ):
            if hasattr(source, key):
                data[key] = getattr(source, key)
    if "corners" not in data:
        data["corners"] = _safe_float(data.get("corners_home")) + _safe_float(data.get("corners_away"))
    if "attack_pressure_diff" not in data and "attack_delta_10m" in data:
        data["attack_pressure_diff"] = data.get("attack_delta_10m")
    return data


def _janitor(features: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from engine.agents_glm.data_janitor_agent import DATA_JANITOR

        return DATA_JANITOR.sanitize_feed(features)
    except Exception:
        return dict(features)


def _elo_note(features: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    home = str(features.get("home") or decision.get("home") or "")
    away = str(features.get("away") or decision.get("away") or "")
    odd = _safe_float(decision.get("odd") or features.get("odd") or 0)
    if not home or not away or odd <= 1:
        return {"ok": True, "value": False, "detail": "Elo sem times/odd suficientes.", "backend": "idle"}
    try:
        from engine.agents_glm.elo_rating_agent import ELO_AGENT

        text = ELO_AGENT.find_value(home, away, odd)
        return {
            "ok": True,
            "value": "VALUE" in str(text).upper(),
            "detail": text,
            "elo_home": ELO_AGENT.get_elo(home),
            "elo_away": ELO_AGENT.get_elo(away),
            "backend": "sqlite",
        }
    except Exception as exc:
        return {"ok": False, "value": False, "detail": f"Elo indisponivel: {exc}", "backend": "error"}


def _local_council(features: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    """Conselho determinístico — não depende de CrewAI/Ollama."""
    quant_says = str(decision.get("decision") or decision.get("final_decision") or "AGUARDA").upper()
    minute = _safe_float(features.get("minute"))
    ap = _safe_float(features.get("attack_pressure_diff"))
    score = str(features.get("score") or "")
    notes = [
        f"Quant: {quant_says}",
        f"minuto={minute:.0f}",
        f"AP_diff={ap:.1f}",
    ]
    risk_veto = []
    if score == "0-0" and minute > 85:
        risk_veto.append("Risk: kill zone 0-0 pos 85'")
    if minute < 30 and quant_says == "ENTRA":
        risk_veto.append("Risk: janela cedo demais para ENTRA")
    if ap < 8 and quant_says == "ENTRA":
        risk_veto.append("Risk: pressao insuficiente para justificar ENTRA")
    if risk_veto:
        return {
            "backend": "local",
            "quant": quant_says,
            "risk": "VETO",
            "verdict": "VETOED",
            "reasons": notes + risk_veto,
        }
    return {
        "backend": "local",
        "quant": quant_says,
        "risk": "APPROVE",
        "verdict": "APPROVED" if quant_says == "ENTRA" else "HOLD",
        "reasons": notes + ["Risk: sem kill zone critica"],
    }


def _crew_council(features: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    enabled = os.environ.get("AURA_CREW_ENABLED", "1").strip() not in {"0", "false", "False"}
    if not enabled:
        return {"backend": "disabled", "verdict": "SKIP", "reasons": ["AURA_CREW_ENABLED=0"]}
    try:
        from engine.agents_glm.crew_council import COUNCIL

        payload = {"features": features, "decision": decision, "paper_trade": True}
        text = COUNCIL.evaluate_trade(str(payload))
        return {"backend": getattr(COUNCIL, "backend", "crew"), "raw": text, "verdict": "ADVISORY", "reasons": [str(text)[:400]]}
    except Exception as exc:
        return {"backend": "unavailable", "verdict": "SKIP", "reasons": [f"CrewAI ausente: {exc}"]}


def _red_team(features: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from engine.agents_glm.red_team_adversary import RED_TEAM

        return RED_TEAM.audit_decision(features, decision)
    except Exception as exc:
        return {"verdict": "APPROVED", "reasons": [f"Red Team indisponivel: {exc}"]}


def _forensics_pending(features: Dict[str, Any], decision: Dict[str, Any], council_verdict: str) -> str:
    try:
        from engine.agents_glm.post_match_forensics import FORENSICS_AGENT

        if council_verdict == "VETOED":
            return FORENSICS_AGENT.execute_autopsy(
                {"minute": features.get("minute"), "score": decision.get("score") or 0, "note": "veto"},
                "LOSS",
            )
        if str(decision.get("decision") or "").upper() == "ENTRA" and council_verdict == "APPROVED":
            from engine.agents.dynamic_thresholds import ONLINE_TUNER

            ONLINE_TUNER.record_result("PENDING", int(_safe_float(features.get("minute"))), int(_safe_float(decision.get("score"))))
            return "PENDING registrado no tuner"
        return "forensics idle"
    except Exception as exc:
        return f"forensics skip: {exc}"


def convene(features: Any, aura_decision: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    raw = features_from_any(features)
    decision = dict(aura_decision or {})
    clean = _janitor(raw)
    elo = _elo_note(clean, decision)
    local = _local_council(clean, decision)
    crew = _crew_council(clean, decision)
    audit = _red_team(clean, decision)

    vetoed = local.get("verdict") == "VETOED" or audit.get("verdict") == "VETOED"
    final = "VETOED" if vetoed else audit.get("verdict", "APPROVED")
    reasons = list(local.get("reasons") or []) + list(audit.get("reasons") or [])
    if elo.get("detail"):
        reasons.append(f"Elo: {elo['detail']}")

    forensics = _forensics_pending(clean, decision, final)
    result = {
        "ok": True,
        "verdict": final,
        "paper_trade": True,
        "execution_allowed": False,
        "plan_only": True,
        "janitor": {"keys": sorted(clean.keys())},
        "elo": elo,
        "local_council": local,
        "crew_council": crew,
        "red_team": audit,
        "forensics": forensics,
        "reasons": reasons,
        "speak": _speak(final, reasons),
    }
    logger.info("Conselho verdict=%s reasons=%s", final, reasons[:3])
    return result


def _speak(verdict: str, reasons: list[str]) -> str:
    first = reasons[0] if reasons else "sem detalhe"
    if verdict == "VETOED":
        return (
            f"O motor queria seguir... [respira] mas o conselho vetou. "
            f"Motivo: {first}. Paper trade only."
        )
    return f"Conselho advisory aprovou a tese. {first}. Sem execucao real."


def record_result(trade_data: Mapping[str, Any], result: str) -> Dict[str, Any]:
    try:
        from engine.agents_glm.post_match_forensics import FORENSICS_AGENT

        summary = FORENSICS_AGENT.execute_autopsy(dict(trade_data), str(result).upper())
        return {"ok": True, "summary": summary, "execution_allowed": False, "paper_trade": True}
    except Exception as exc:
        return {"ok": False, "summary": str(exc), "execution_allowed": False, "paper_trade": True}
