# Pacote de melhorias implementáveis (v12.8.x + Teorias Reversa Frentes 1-3)
from .telemetry_schema import validate_payload, clamp_stats
from .frame_cache import FrameCache
from .rate_limit import RateLimiter
from .trading_mode import TradingMode, get_mode
from .model_checksum import sha256_file, verify_weights
from .structured_log import log_event
from .slo import SLO
from .prompt_profiles import sampling_for_task
from .health_agg import build_health
from .notify_policy import should_notify
from .token_bucket import AdaptiveTokenBucket

# v12.8.0 — Interatividade e acertividade
from .interactive_coach import InteractiveCoach, get_coach, UserFeedback
from .accuracy_boost import (
    ensemble_probability,
    scenario_what_if,
    calibrate_confidence,
    quality_gate_reinforced,
    build_accuracy_report,
    EnsembleResult,
)
from .voice_interactivity import (
    detect_intent,
    build_voice_response_package,
    sanitize_for_tts,
)

# Teoria Reversa — Frentes 1-3 (produção)
from .hlc_clock import (
    HybridLogicalClockManager,
    get_hlc_manager,
    envelope_from_raw,
    NodeId,
    HLC,
)
from .risk_veracity import (
    VeracityRiskEngine,
    get_veracity_engine,
    evaluate_risk,
    FieldSnapshot,
    VeracityResult,
    cubic_smooth_kappa,
    gamma_age,
    kelly_fractional,
)
from .latency_allocator import (
    PredictiveLatencyBudgetAllocator,
    get_latency_allocator,
    Priority,
    LatencyBudget,
)

__all__ = [
    "validate_payload",
    "clamp_stats",
    "FrameCache",
    "RateLimiter",
    "TradingMode",
    "get_mode",
    "sha256_file",
    "verify_weights",
    "log_event",
    "SLO",
    "sampling_for_task",
    "build_health",
    "should_notify",
    "AdaptiveTokenBucket",
    "InteractiveCoach",
    "get_coach",
    "UserFeedback",
    "ensemble_probability",
    "scenario_what_if",
    "calibrate_confidence",
    "quality_gate_reinforced",
    "build_accuracy_report",
    "EnsembleResult",
    "detect_intent",
    "build_voice_response_package",
    "sanitize_for_tts",
    "HybridLogicalClockManager",
    "get_hlc_manager",
    "envelope_from_raw",
    "NodeId",
    "HLC",
    "VeracityRiskEngine",
    "get_veracity_engine",
    "evaluate_risk",
    "FieldSnapshot",
    "VeracityResult",
    "cubic_smooth_kappa",
    "gamma_age",
    "kelly_fractional",
    "PredictiveLatencyBudgetAllocator",
    "get_latency_allocator",
    "Priority",
    "LatencyBudget",
    "IsotonicCalibrator",
    "walk_forward_evaluate",
    "FeatureDriftMonitor",
    "DomApiCaptureCanary",
    "risk_table_as_dict",
    "validate_request_token",
]

# Calibration / Drift / Canary / Risk / Auth
from .calibration_lab import (
    IsotonicCalibrator,
    walk_forward_evaluate,
    brier_score,
    log_loss,
    expected_calibration_error,
)
from .drift_monitor import FeatureDriftMonitor, DriftAlert
from .dom_canary import DomApiCaptureCanary
from .risk_table import risk_table_as_dict, highest_severity, RISK_CATALOG
from .local_auth import validate_request_token, is_hardened, generate_install_token


from .pipeline_hooks import enrich_telemetry, enrich_analysis
