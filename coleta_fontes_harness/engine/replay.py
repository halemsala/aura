"""P0 Fase 2 — Replay determinístico mínimo por fixture_id.

Reproduz decisões a partir de raw_events sem alterar decision_logs reais.
Compara signal/probabilidade e reporta a primeira divergência.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from data_store import list_raw_events, list_decision_logs, get_decision_log


def _load_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("payload_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def replay_fixture(
    fixture_id: str,
    *,
    model_version: Optional[str] = None,
    path: Optional[str] = None,
    engine=None,
) -> Dict[str, Any]:
    """
    Replay all raw events for fixture_id in original order.
    Does NOT write to decision_logs (shadow comparison only).
    """
    fid = str(fixture_id).strip()
    if not fid:
        return {"ok": False, "error": "fixture_id_missing"}

    if engine is None:
        from engine_core import LocalAIEngine
        engine = LocalAIEngine()

    events = list_raw_events(fid, path=path)
    registered = list_decision_logs(fid, path=path)

    if not events:
        return {
            "ok": True,
            "fixture_id": fid,
            "events": 0,
            "registered_decisions": len(registered),
            "replayed": [],
            "divergences": [],
            "message": "no raw_events for fixture",
        }

    replayed: List[Dict[str, Any]] = []
    divergences: List[Dict[str, Any]] = []

    for i, row in enumerate(events):
        payload = _load_payload(row)
        payload["fixtureId"] = fid
        analysis = engine.ingest(payload, write_ledger=False)
        entry = {
            "index": i,
            "event_id": row.get("event_id"),
            "signal": analysis.get("signal"),
            "decision": analysis.get("decision") or analysis.get("signal"),
            "corner_prob": analysis.get("corner_prob"),
            "integrity_status": (analysis.get("data_integrity") or {}).get("status"),
            "model_version": model_version or "localai-12.7.16-p0",
        }
        replayed.append(entry)

        if i < len(registered):
            reg = registered[i]
            reg_signal = str(reg.get("signal") or "")
            rep_signal = str(entry["signal"] or "")
            same_action = reg_signal == rep_signal
            if not same_action:
                divergences.append({
                    "decision_id": reg.get("decision_id"),
                    "index": i,
                    "same_action": False,
                    "registered": reg_signal,
                    "replayed": rep_signal,
                    "first_diff": "signal",
                    "registered_model_version": reg.get("model_version"),
                    "replayed_model_version": entry["model_version"],
                    "registered_prob": reg.get("corner_prob"),
                    "replayed_prob": entry.get("corner_prob"),
                })
            else:
                try:
                    rp = float(reg.get("corner_prob") or 0)
                    pp = float(entry.get("corner_prob") or 0)
                    if abs(rp - pp) > 1e-4:
                        divergences.append({
                            "decision_id": reg.get("decision_id"),
                            "index": i,
                            "same_action": True,
                            "registered": reg_signal,
                            "replayed": rep_signal,
                            "first_diff": "corner_prob",
                            "registered_prob": rp,
                            "replayed_prob": pp,
                            "registered_model_version": reg.get("model_version"),
                            "replayed_model_version": entry["model_version"],
                        })
                except (TypeError, ValueError):
                    pass

    first = divergences[0] if divergences else None
    return {
        "ok": True,
        "fixture_id": fid,
        "events": len(events),
        "registered_decisions": len(registered),
        "replayed_count": len(replayed),
        "divergences": divergences,
        "first_divergence": first,
        "replayed": replayed,
        "model_version": model_version or "localai-12.7.16-p0",
    }


def compare_decision(decision_id: str, path: Optional[str] = None, engine=None) -> Dict[str, Any]:
    reg = get_decision_log(decision_id, path=path)
    if not reg:
        return {"ok": False, "error": "decision_not_found", "decision_id": decision_id}
    fid = reg.get("fixture_id")
    result = replay_fixture(str(fid), path=path, engine=engine)
    result["requested_decision_id"] = decision_id
    return result
