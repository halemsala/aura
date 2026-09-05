"""P1 Fase 5 — Hard Risk Gates independentes.

Gates (ordem de avaliação):
1. fixture_gate
2. data_quality_gate
3. event_coherence_gate
4. model_loaded_gate
5. calibration_gate
6. uncertainty_gate
7. market_freshness_gate
8. edge_gate (somente se mercado semanticamente compatível com o alvo)
9. cooldown_gate
10. exposure_gate (desativado em modo observação / Kelly off)
11. policy_decision

Kelly permanece DESLIGADO. Mercado over_9_5 NÃO é equivalente a next_corner.

PATCH V23-P2 (item 1.3 da auditoria): RISK_GATES é singleton de processo
(instanciado uma vez, linha final deste arquivo) e self.cooldowns /
self.hysteresis são dicts mutáveis de instância. evaluate() é o único
ponto de entrada público e orquestra: detect_and_apply_event_cooldowns
(escreve self.cooldowns) -> 10 gates, dois dos quais leem
self.cooldowns/self.hysteresis (gate_cooldown le cooldowns; a chamada a
apply_hysteresis fora do loop de gates le+escreve hysteresis) -> leitura
final de self.cooldowns[fid]/self.hysteresis[fid] para montar o dict de
retorno. Sem serialização, duas chamadas concorrentes de evaluate() para
o mesmo fixture_id (dois requests HTTP simultâneos da mesma partida, por
exemplo) podem intercalar entre essas etapas: uma leitura de hysteresis
pode ver o cooldown já aplicado pela outra chamada mas não o hysteresis
já atualizado por ela, produzindo uma decisão inconsistente com nenhuma
das duas chamadas isoladamente.

self._lock (threading.Lock, não asyncio.Lock) agora envolve o corpo
inteiro de evaluate() e de trigger_cooldown() quando chamado fora de
evaluate(). threading.Lock foi escolhido em vez de asyncio.Lock porque
nenhum método desta classe é `async def` — este é código síncrono que
pode ser invocado tanto de uma rota async via threadpool (ex.: FastAPI
com `run_in_threadpool`) quanto de uma thread worker direta; um
asyncio.Lock só serializa dentro do mesmo event loop e não protegeria
contra a segunda hipótese. O lock é reentrante (RLock) porque
evaluate() chama detect_and_apply_event_cooldowns(), que por sua vez
chama trigger_cooldown() — com Lock simples (não-reentrante) isso
causaria deadlock da própria thread.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# --- Constantes de política ---

KELLY_ENABLED = False  # hard-off até validação completa
OBSERVATION_MODE = True  # não libera stake real

# Cooldown triggers
COOLDOWN_AFTER_GOAL_SEC = 90.0
COOLDOWN_AFTER_RED_SEC = 120.0
COOLDOWN_AFTER_HALFTIME_SEC = 180.0
COOLDOWN_AFTER_ROLLBACK_SEC = 60.0
COOLDOWN_AFTER_DISCONNECT_SEC = 45.0
COOLDOWN_AFTER_SIGNAL_SEC = 120.0

# Histerese: entrada mais exigente que permanência
HYSTERESIS_ENTER_PROB = 0.72
HYSTERESIS_STAY_PROB = 0.60
HYSTERESIS_ENTER_EDGE = 0.05
HYSTERESIS_STAY_EDGE = 0.02

# Uncertainty / freshness
MAX_UNCERTAINTY = 0.55
MAX_ODDS_AGE_SEC = 30.0
MAX_CAPTURE_AGE_WARN_SEC = 15.0

# Mercado semanticamente compatível com next_corner_within_horizon
COMPATIBLE_MARKETS = (
    "next_corner",
    "corner_next",
    "escanteio_proximo",
    "corners_live",
    "escanteios_ao_vivo",
    "corner_5min",
    "next_corner_within_300s",
)
INCOMPATIBLE_MARKETS = (
    "over_9_5",
    "over_9.5",
    "under_9_5",
    "match_total_corners",
    "total_corners",
    "asian_total",
)


@dataclass
class GateResult:
    name: str
    passed: bool
    code: str = "OK"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CooldownState:
    fixture_id: str
    until_ts: float = 0.0
    reason: str = ""
    source_event: str = ""

    def active(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return now < self.until_ts

    def remaining(self, now: Optional[float] = None) -> float:
        now = now if now is not None else time.time()
        return max(0.0, self.until_ts - now)


@dataclass
class HysteresisState:
    fixture_id: str
    in_watch: bool = False
    last_prob: float = 0.0
    last_edge: float = 0.0


class RiskGateEngine:
    """Hard gates independentes + cooldown + histerese. Kelly off."""

    def __init__(self) -> None:
        self.cooldowns: Dict[str, CooldownState] = {}
        self.hysteresis: Dict[str, HysteresisState] = {}
        self.kelly_enabled = KELLY_ENABLED
        self.observation_mode = OBSERVATION_MODE
        # PATCH V23-P2: RLock (não Lock) — reentrante porque evaluate()
        # chama detect_and_apply_event_cooldowns() -> trigger_cooldown()
        # na mesma thread, sob o mesmo lock.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Cooldown management
    # ------------------------------------------------------------------
    def trigger_cooldown(
        self,
        fixture_id: str,
        reason: str,
        duration_sec: float,
        *,
        source_event: str = "",
    ) -> CooldownState:
        with self._lock:
            fid = str(fixture_id)
            until = time.time() + max(0.0, duration_sec)
            prev = self.cooldowns.get(fid)
            if prev and prev.until_ts > until:
                # keep longer cooldown
                prev.reason = reason
                prev.source_event = source_event or prev.source_event
                return prev
            st = CooldownState(fixture_id=fid, until_ts=until, reason=reason, source_event=source_event)
            self.cooldowns[fid] = st
            return st

    def detect_and_apply_event_cooldowns(
        self,
        fixture_id: str,
        payload: Dict[str, Any],
        integrity: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Scan payload/integrity for cooldown triggers. Returns list of reasons applied."""
        applied: List[str] = []
        fid = str(fixture_id)
        integrity = integrity or {}
        issues = list(integrity.get("issues") or [])

        # clock rollback
        if any("rollback" in str(x).lower() or "clock_rollback" in str(x).lower() for x in issues):
            self.trigger_cooldown(fid, "CLOCK_ROLLBACK", COOLDOWN_AFTER_ROLLBACK_SEC, source_event="integrity")
            applied.append("CLOCK_ROLLBACK")

        # stale / disconnect style
        if "capture_stale_over_45s" in issues or "LEDGER_UNAVAILABLE" in issues:
            self.trigger_cooldown(fid, "CAPTURE_LOSS", COOLDOWN_AFTER_DISCONNECT_SEC, source_event="integrity")
            applied.append("CAPTURE_LOSS")

        status = str(payload.get("liveStatus") or payload.get("status") or "").upper()
        if any(x in status for x in ("HT", "HALF", "INTERVAL")):
            self.trigger_cooldown(fid, "HALFTIME", COOLDOWN_AFTER_HALFTIME_SEC, source_event="status")
            applied.append("HALFTIME")

        events = payload.get("events") or payload.get("eventos") or []
        if isinstance(events, list):
            for ev in events[-8:]:  # recent tail
                if not isinstance(ev, dict):
                    blob = str(ev).lower()
                else:
                    blob = " ".join(str(ev.get(k) or "") for k in ("type", "event", "name", "kind")).lower()
                if "goal" in blob or "gol" in blob:
                    self.trigger_cooldown(fid, "GOAL", COOLDOWN_AFTER_GOAL_SEC, source_event="event")
                    applied.append("GOAL")
                if "red" in blob or "vermelho" in blob or "card-red" in blob:
                    self.trigger_cooldown(fid, "RED_CARD", COOLDOWN_AFTER_RED_SEC, source_event="event")
                    applied.append("RED_CARD")

        # explicit flags from payload
        if payload.get("connection_lost") or payload.get("capture_lost"):
            self.trigger_cooldown(fid, "DISCONNECT", COOLDOWN_AFTER_DISCONNECT_SEC, source_event="flag")
            applied.append("DISCONNECT")

        return applied

    # ------------------------------------------------------------------
    # Individual gates
    # ------------------------------------------------------------------
    def gate_fixture(self, analysis: Dict[str, Any], payload: Dict[str, Any]) -> GateResult:
        fid = str(analysis.get("fixtureId") or payload.get("fixtureId") or "").strip()
        home = str(payload.get("home") or analysis.get("home") or "").strip()
        away = str(payload.get("away") or analysis.get("away") or "").strip()
        if not fid:
            return GateResult("fixture_gate", False, "FIXTURE_MISSING", "Sem entrada — fixtureId ausente (modo observação)")
        if not home or not away or home == away:
            return GateResult("fixture_gate", False, "TEAMS_INVALID", "times ausentes ou inválidos")
        return GateResult("fixture_gate", True, "OK", "fixture ok")

    def gate_data_quality(self, analysis: Dict[str, Any]) -> GateResult:
        integrity = analysis.get("data_integrity") or {}
        status = str(integrity.get("status") or "")
        signal = str(analysis.get("signal") or "")
        if signal in ("BLOCKED_BY_DATA", "BLOCKED_BY_LEDGER"):
            return GateResult(
                "data_quality_gate", False, signal,
                "bloqueado por qualidade/ledger",
                {"issues": integrity.get("issues") or []},
            )
        if status == "BLOCK":
            return GateResult(
                "data_quality_gate", False, "INTEGRITY_BLOCK",
                "integridade BLOCK",
                {"issues": integrity.get("issues") or []},
            )
        crit = (analysis.get("feature_quality") or {}).get("critical_missing_fields") or []
        if crit:
            return GateResult(
                "data_quality_gate", False, "CRITICAL_FEATURES",
                "features críticas ausentes",
                {"fields": crit},
            )
        return GateResult("data_quality_gate", True, "OK", "data quality ok", {
            "warnings": integrity.get("warnings") or [],
        })

    def gate_event_coherence(self, analysis: Dict[str, Any], payload: Dict[str, Any]) -> GateResult:
        integrity = analysis.get("data_integrity") or {}
        issues = list(integrity.get("issues") or [])
        bad = [x for x in issues if "conflict" in str(x).lower() or "mismatch" in str(x).lower()]
        if bad:
            return GateResult("event_coherence_gate", False, "COHERENCE_FAIL", "conflito de eventos/stats", {"issues": bad})
        return GateResult("event_coherence_gate", True, "OK", "coerência ok")

    def gate_model_loaded(self, analysis: Dict[str, Any]) -> GateResult:
        # baseline path always present; shadow optional
        if analysis.get("corner_prob") is None and analysis.get("signal") not in (
            "BLOCKED_BY_DATA", "BLOCKED_BY_LEDGER", "BLOCK",
        ):
            return GateResult("model_loaded_gate", False, "MODEL_MISSING", "probabilidade ausente")
        return GateResult("model_loaded_gate", True, "OK", "modelo baseline presente")

    def gate_calibration(self, analysis: Dict[str, Any]) -> GateResult:
        # Shadow calibrator is informational; live path may lack explicit calibrator.
        # Block BUY only if explicitly marked uncalibrated.
        if analysis.get("model_uncalibrated") is True:
            return GateResult("calibration_gate", False, "MODEL_UNCALIBRATED", "modelo sem calibração")
        return GateResult("calibration_gate", True, "OK", "calibração ok ou não exigida no baseline")

    def gate_uncertainty(self, analysis: Dict[str, Any]) -> GateResult:
        try:
            u = float(analysis.get("uncertainty") if analysis.get("uncertainty") is not None else 1.0 - float(analysis.get("corner_prob") or 0))
        except (TypeError, ValueError):
            u = 1.0
        if u > MAX_UNCERTAINTY and str(analysis.get("signal") or "").startswith("BUY"):
            return GateResult("uncertainty_gate", False, "UNCERTAINTY_HIGH", f"incerteza {u:.3f} > {MAX_UNCERTAINTY}")
        return GateResult("uncertainty_gate", True, "OK", "incerteza aceitável", {"uncertainty": u})

    def gate_market_freshness(self, analysis: Dict[str, Any], payload: Dict[str, Any]) -> GateResult:
        odds_ts = payload.get("odds_ts") or payload.get("oddsTimestamp") or analysis.get("odds_ts")
        if odds_ts is None:
            # missing odds is not automatic hard fail for observation; edge_gate handles BUY
            return GateResult("market_freshness_gate", True, "ODDS_ABSENT", "odds ausentes (ok em observação)")
        try:
            ts = float(odds_ts)
            if ts > 10_000_000_000:
                ts = ts / 1000.0
            age = time.time() - ts
            if age > MAX_ODDS_AGE_SEC:
                return GateResult(
                    "market_freshness_gate", False, "ODDS_STALE",
                    f"odds velhas ({age:.1f}s > {MAX_ODDS_AGE_SEC}s)",
                    {"age_sec": age},
                )
        except (TypeError, ValueError):
            return GateResult("market_freshness_gate", False, "ODDS_TS_INVALID", "timestamp de odds inválido")
        return GateResult("market_freshness_gate", True, "OK", "odds frescas")

    def gate_edge(
        self,
        analysis: Dict[str, Any],
        payload: Dict[str, Any],
        *,
        require_for_buy: bool = True,
    ) -> GateResult:
        signal = str(analysis.get("signal") or "")
        market_name = (
            analysis.get("market")
            or payload.get("market")
            or payload.get("market_name")
            or ""
        )
        price = analysis.get("price") or payload.get("odds") or payload.get("price")
        odds_ts = payload.get("odds_ts") or payload.get("oddsTimestamp") or analysis.get("odds_ts")
        try:
            prob = float(analysis.get("corner_prob") or 0)
        except (TypeError, ValueError):
            prob = 0.0

        try:
            from market_edge import compute_edge
            edge_info = compute_edge(prob, price, market_name=market_name, odds_ts=odds_ts)
        except Exception as exc:
            edge_info = {"compatible": False, "code": "EDGE_MODULE_ERROR", "message": str(exc), "edge": None}

        analysis["market_edge"] = edge_info
        if edge_info.get("edge") is not None:
            analysis["edge"] = edge_info["edge"]
        if edge_info.get("implied_prob") is not None:
            analysis["market_prob"] = edge_info["implied_prob"]

        if signal.startswith("BUY"):
            if edge_info.get("code") == "MARKET_INCOMPATIBLE_TOTAL":
                return GateResult(
                    "edge_gate", False, "MARKET_INCOMPATIBLE",
                    edge_info.get("message") or "mercado total incompatível",
                    edge_info,
                )
            if not edge_info.get("compatible"):
                return GateResult(
                    "edge_gate", False, str(edge_info.get("code") or "NO_EDGE"),
                    edge_info.get("message") or "edge não operacional",
                    edge_info,
                )
            edge = float(edge_info.get("edge") or 0)
            if edge < HYSTERESIS_ENTER_EDGE:
                return GateResult(
                    "edge_gate", False, "EDGE_TOO_LOW",
                    f"edge {edge:.4f} < {HYSTERESIS_ENTER_EDGE}",
                    edge_info,
                )
            return GateResult("edge_gate", True, "OK", "edge positivo next_corner", edge_info)

        return GateResult("edge_gate", True, "OK", "edge não exigido fora de BUY", edge_info)

    def gate_cooldown(self, fixture_id: str) -> GateResult:
        # Leitura protegida: consistente com o que trigger_cooldown() acabou
        # de escrever na mesma chamada de evaluate(), sob o mesmo self._lock.
        with self._lock:
            st = self.cooldowns.get(str(fixture_id))
            if st and st.active():
                return GateResult(
                    "cooldown_gate", False, "COOLDOWN",
                    f"cooldown ativo: {st.reason} ({st.remaining():.0f}s restantes)",
                    {"reason": st.reason, "remaining_sec": st.remaining(), "until_ts": st.until_ts},
                )
            return GateResult("cooldown_gate", True, "OK", "sem cooldown")

    def gate_exposure(self, analysis: Dict[str, Any]) -> GateResult:
        """Kelly/stake real desligados — sempre bloqueia exposição operacional."""
        if self.observation_mode or not self.kelly_enabled:
            # In observation mode exposure gate always "passes" as informational block on stake
            return GateResult(
                "exposure_gate", True, "KELLY_DISABLED",
                "Kelly desligado; exposição real = 0",
                {"kelly_enabled": False, "observation_mode": True, "stake_pct": 0.0},
            )
        # future path when Kelly enabled would check bankroll etc.
        return GateResult("exposure_gate", False, "EXPOSURE_BLOCKED", "exposição não autorizada")

    def apply_hysteresis(
        self,
        fixture_id: str,
        signal: str,
        prob: float,
        edge: Optional[float],
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Enter WATCH/BUY requires higher bar; stay in WATCH with lower bar.
        Returns possibly adjusted signal + meta.
        """
        with self._lock:
            fid = str(fixture_id)
            st = self.hysteresis.get(fid) or HysteresisState(fixture_id=fid)
            edge_v = float(edge) if edge is not None else 0.0
            meta = {"hysteresis_in_watch": st.in_watch, "enter_prob": HYSTERESIS_ENTER_PROB, "stay_prob": HYSTERESIS_STAY_PROB}

            if signal in ("BUY_CORNER", "WATCH_CORNER"):
                if not st.in_watch:
                    # entry bar
                    if prob < HYSTERESIS_ENTER_PROB and signal == "BUY_CORNER":
                        signal = "WATCH_CORNER"
                        meta["action"] = "downgrade_buy_to_watch_entry_bar"
                    elif prob < HYSTERESIS_STAY_PROB:
                        signal = "HOLD"
                        meta["action"] = "reject_entry_low_prob"
                    else:
                        st.in_watch = True
                        meta["action"] = "enter_watch"
                else:
                    # stay bar softer
                    if prob < HYSTERESIS_STAY_PROB:
                        signal = "HOLD"
                        st.in_watch = False
                        meta["action"] = "exit_watch"
                    elif signal == "BUY_CORNER" and edge_v < HYSTERESIS_STAY_EDGE:
                        signal = "WATCH_CORNER"
                        meta["action"] = "downgrade_buy_low_edge_stay"
                    else:
                        meta["action"] = "stay"
            else:
                if st.in_watch and signal in ("HOLD", "WATCH_ATTACK"):
                    st.in_watch = False
                    meta["action"] = "clear_watch"

            st.last_prob = prob
            st.last_edge = edge_v
            self.hysteresis[fid] = st
            meta["hysteresis_in_watch"] = st.in_watch
            return signal, meta

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    def evaluate(
        self,
        analysis: Dict[str, Any],
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # PATCH V23-P2 (item 1.3): todo o corpo de evaluate() roda sob
        # self._lock. Isto serializa evaluate() por instância de
        # RiskGateEngine (singleton de processo RISK_GATES) — duas
        # chamadas concorrentes, mesmo para fixture_id diferentes, agora
        # executam em sequência em vez de intercaladas. Para o volume
        # esperado (avaliação de risco de partidas ao vivo, não um hot
        # path de milhares de req/s) isto é uma troca aceitável: a
        # alternativa seria um lock por fixture_id, mais granular mas
        # bem mais complexa de manter correta (precisa de limpeza de
        # locks órfãos por fixture_id encerrado). Se o volume de
        # avaliações concorrentes crescer a ponto deste lock global virar
        # gargalo mensurável, revisitar com lock por fixture_id.
        with self._lock:
            payload = payload or {}
            fid = str(analysis.get("fixtureId") or payload.get("fixtureId") or "").strip()

            # Apply event-driven cooldowns first
            cd_applied = self.detect_and_apply_event_cooldowns(
                fid, payload, analysis.get("data_integrity") or {},
            )

            gates: List[GateResult] = [
                self.gate_fixture(analysis, payload),
                self.gate_data_quality(analysis),
                self.gate_event_coherence(analysis, payload),
                self.gate_model_loaded(analysis),
                self.gate_calibration(analysis),
                self.gate_uncertainty(analysis),
                self.gate_market_freshness(analysis, payload),
                self.gate_edge(analysis, payload),
                self.gate_cooldown(fid),
                self.gate_exposure(analysis),
            ]

            failed = [g for g in gates if not g.passed]
            # risk_score only explanatory — hard gates dominate
            risk_score = sum(1 for g in failed) / max(1, len(gates))

            try:
                prob = float(analysis.get("corner_prob") or 0.0)
            except (TypeError, ValueError):
                prob = 0.0
            edge = analysis.get("edge")
            try:
                edge_f = float(edge) if edge is not None else None
            except (TypeError, ValueError):
                edge_f = None

            signal = str(analysis.get("signal") or "HOLD")
            # Preserve data/ledger blocks
            if signal in ("BLOCKED_BY_DATA", "BLOCKED_BY_LEDGER"):
                decision = signal
                approved = False
            elif failed:
                # Map first hard failure to decision code
                first = failed[0]
                mapping = {
                    "data_quality_gate": "BLOCKED_BY_DATA",
                    "fixture_gate": "BLOCKED_BY_DATA",
                    "event_coherence_gate": "BLOCKED_BY_DATA",
                    "model_loaded_gate": "BLOCKED_BY_MODEL",
                    "calibration_gate": "BLOCKED_BY_MODEL",
                    "uncertainty_gate": "BLOCKED_BY_RISK",
                    "market_freshness_gate": "BLOCKED_BY_MARKET",
                    "edge_gate": "BLOCKED_BY_MARKET",
                    "cooldown_gate": "BLOCKED_BY_RISK",
                    "exposure_gate": "BLOCKED_BY_RISK",
                }
                decision = mapping.get(first.name, "BLOCKED_BY_RISK")
                approved = False
                if signal.startswith("BUY"):
                    signal = decision
            else:
                # hysteresis on non-blocked path
                signal, hyst_meta = self.apply_hysteresis(fid, signal, prob, edge_f)
                decision = signal
                approved = False  # never auto-approve real stake while Kelly off / observation
                # Even if signal still BUY_CORNER, observation mode forces approved=false
                if signal == "BUY_CORNER" and not self.observation_mode and self.kelly_enabled:
                    approved = True  # unreachable while flags off
                else:
                    approved = False
                    if signal == "BUY_CORNER":
                        # Downgrade operational approval: keep signal visible but not executable
                        decision = "BUY_CORNER"
                        # still not approved
                hyst_meta = hyst_meta if "hyst_meta" in dir() else {}

            # force kelly/stake zero
            kelly = 0.0
            stake_pct = 0.0
            exposure = 0.0

            result = {
                "gates": [g.to_dict() for g in gates],
                "failed_gates": [g.name for g in failed],
                "risk_score": round(risk_score, 4),
                "signal": signal,
                "decision": decision,
                "approved": approved,
                "kelly": kelly,
                "stake_pct": stake_pct,
                "exposure": exposure,
                "kelly_enabled": self.kelly_enabled,
                "observation_mode": self.observation_mode,
                "cooldown_applied": cd_applied,
                "cooldown": (
                    {
                        "active": self.cooldowns[fid].active(),
                        "reason": self.cooldowns[fid].reason,
                        "remaining_sec": self.cooldowns[fid].remaining(),
                    }
                    if fid in self.cooldowns else {"active": False}
                ),
                "hysteresis": (
                    asdict(self.hysteresis[fid]) if fid in self.hysteresis else {}
                ),
                "policy": "p1_hard_gates_v1",
            }
            return result


# Process singleton
RISK_GATES = RiskGateEngine()

# --- V23 BLOCO 7: calibração isotonica (opcional) ---
def calibrated_threshold_prob(raw_prob: float) -> float:
    try:
        from probability_calibrator import calibrator
        return float(calibrator.get_calibrated_prob(raw_prob))
    except Exception:
        return float(raw_prob or 0.0)


# --- V23: calibracao simples por streak (sem hardcode unico 0.72) ---
# PATCH V23-P2: mesma classe de bug do item 1.3, encontrada ao reler este
# arquivo por completo para o patch — streak_calibrator é outro singleton
# de módulo (linha final deste arquivo) com estado mutável (self._recent,
# self.threshold) sem lock. record() faz o mesmo padrão read-modify-write
# de RiskGateEngine antes deste patch. Não fazia parte do item 1.3 original
# (que citava apenas RiskGateEngine) — corrigido aqui por ser a mesma
# causa raiz no mesmo arquivo, para não deixar half-fixed. Se preferir
# tratar como patch separado, reverta apenas a classe abaixo.
class SimpleStreakCalibrator:
    def __init__(self, base_threshold: float = 0.60):
        self.base = float(base_threshold)
        self.threshold = float(base_threshold)
        self._recent: List[bool] = []  # True=acerto, False=erro
        self._lock = threading.Lock()

    def record(self, correct: bool) -> None:
        with self._lock:
            self._recent.append(bool(correct))
            self._recent = self._recent[-5:]
            if len(self._recent) < 5:
                return
            if all(not x for x in self._recent):
                self.threshold = min(0.90, self.threshold + 0.05)
            elif all(x for x in self._recent):
                self.threshold = max(0.50, self.threshold - 0.05)

    def should_enter(self, calibrated_prob: float) -> bool:
        # leitura de self.threshold: em CPython, leitura de float é atômica
        # via GIL; não precisa do lock para uma leitura isolada.
        return float(calibrated_prob or 0.0) >= self.threshold


streak_calibrator = SimpleStreakCalibrator()
