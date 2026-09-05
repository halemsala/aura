# pipeline_hooks.py
# Integração dos módulos 12.8.x no caminho de telemetria/análise
# Paper-first. Nunca aprova stake real.

from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Imports defensivos — sistema continua se algum módulo falhar
try:
    from .dom_canary import DomApiCaptureCanary
except Exception:
    DomApiCaptureCanary = None  # type: ignore

try:
    from .drift_monitor import FeatureDriftMonitor
except Exception:
    FeatureDriftMonitor = None  # type: ignore

try:
    from .hlc_clock import get_hlc_manager
except Exception:
    get_hlc_manager = None  # type: ignore

try:
    from .risk_veracity import evaluate_risk
except Exception:
    evaluate_risk = None  # type: ignore

try:
    from .risk_table import risk_table_as_dict, highest_severity
except Exception:
    risk_table_as_dict = None  # type: ignore
    highest_severity = None  # type: ignore

_canary = DomApiCaptureCanary() if DomApiCaptureCanary else None
_drift = FeatureDriftMonitor() if FeatureDriftMonitor else None


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def enrich_telemetry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chamado no início do ingest.
    - Marca batidas no Canary (WoM, pressure, odds, xG…)
    - Atualiza drift monitor
    - Carimba HLC se disponível
    """
    out = dict(payload) if payload else {}
    now = time.time()

    # --- Canary beats ---
    if _canary is not None:
        sources = {
            "odds": out.get("odds") or out.get("odds_last"),
            "odds_velocity": out.get("odds_velocity") or out.get("velocity"),
            "pressure": out.get("pressure_slope") or out.get("pressure"),
            "wom": out.get("wom") or out.get("wom_imbalance"),
            "xg": out.get("xg") or out.get("xG"),
            "corners": out.get("corners") or out.get("corner_count"),
            "events": out.get("events"),
        }
        for name, val in sources.items():
            if val is None or val == "" or val == [] or val == {}:
                _canary.fail(name)
            else:
                _canary.beat(name, val)
        out["_canary"] = _canary.evaluate()

    # --- Drift ---
    if _drift is not None:
        feats = {}
        for k in ("pressure_slope", "odds_velocity", "wom", "xg_home", "xg_away"):
            v = _num(out.get(k))
            if v is not None:
                feats[k] = v
        # nested pressure
        if "pressure" in out and isinstance(out["pressure"], (int, float)):
            feats["pressure"] = float(out["pressure"])
        alerts = _drift.update(feats)
        out["_drift_alerts"] = [
            {"feature": a.feature, "severity": a.severity, "message": a.message, "z": a.value}
            for a in alerts
        ]

    # --- HLC stamp ---
    if get_hlc_manager is not None:
        try:
            mgr = get_hlc_manager()
            env = mgr.generate_local_event({"fixtureId": out.get("fixtureId")})
            out["_hlc"] = env.get("hlc")
            out["_vc"] = env.get("vc")
        except Exception:
            pass

    out["_hooks_ts"] = now
    return out


def enrich_analysis(analysis: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Chamado após análise / risk.
    Anexa veracity-kelly contínuo, canary status e risk table summary.
    Nunca altera approved para True.
    """
    a = dict(analysis) if analysis else {}
    payload = payload or {}

    # Canary já pode estar no payload
    canary = payload.get("_canary") or ( _canary.evaluate() if _canary else None )
    if canary:
        a["capture_canary"] = canary
        if canary.get("any_critical"):
            # reforça bloqueio por dados sem quebrar contrato existente
            di = dict(a.get("data_integrity") or {})
            issues = list(di.get("issues") or [])
            if "SOURCE_INACTIVE" not in issues:
                issues.append("SOURCE_INACTIVE")
            di["issues"] = issues
            if di.get("status") != "BLOCK":
                di["status"] = "WARN"
            a["data_integrity"] = di

    # Veracity + continuous Kelly damping (informativo; stake continua 0)
    if evaluate_risk is not None:
        try:
            hlc_pt = int(time.time() * 1000)
            if payload.get("_hlc") and isinstance(payload["_hlc"], (list, tuple)):
                hlc_pt = int(payload["_hlc"][0])
            model_prob = float(a.get("corner_prob") or a.get("probability") or 0.5)
            odds = payload.get("odds") or a.get("odds") or 2.0
            try:
                decimal_odds = float(odds) if not isinstance(odds, dict) else float(odds.get("back") or odds.get("value") or 2.0)
            except Exception:
                decimal_odds = 2.0
            vr = evaluate_risk(payload, model_prob, decimal_odds, hlc_pt)
            a["veracity_risk"] = {
                "V": vr.V,
                "kappa": vr.kappa,
                "gamma_age": vr.gamma_age,
                "delta_t_s": vr.delta_t_s,
                "f_star": vr.f_star,
                "f_final": vr.f_final,
                "action": vr.action,
                "note": "paper-first: f_final é informativo; approved permanece false",
            }
        except Exception as exc:
            a["veracity_risk"] = {"error": str(exc)}

    # Risk catalog snapshot
    if risk_table_as_dict is not None:
        try:
            a["risk_catalog_severity"] = highest_severity() if highest_severity else "UNKNOWN"
            a["risk_catalog_active"] = [r["code"] for r in risk_table_as_dict(active_only=True)][:12]
        except Exception:
            pass

    # Garantia soberana
    a["approved"] = False
    return a
