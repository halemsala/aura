#!/usr/bin/env python3
"""Secure, dependency-light control-plane primitives for AURA Quant-X.

The module provides PolicyGate, risk analysis, GLMPlanner, structured-plan
verification, DAG execution with rollback, and AuditLedger persistence. It does
not expose arbitrary shell execution, does not place real orders, and never
lets a model decide its own authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence

CANONICAL_DB_PATH = Path("engine/aura_quant_x.db")
MAX_PLAN_STEPS = 32
MAX_TEXT = 64_000
MAX_MAPPING_ITEMS = 256
MAX_PLAN_DOCUMENT_CHARS = 128_000
MAX_SCHEMA_DEPTH = 8
MAX_SCHEMA_ITEMS = 200
MAX_EMBEDDING_DIM = 8_192
GENESIS_HASH = "AURA-GENESIS-v1"
_MEMORY_STATUSES = frozenset({"PLANNED", "APPROVED", "COMPLETED", "FAILED", "BLOCKED", "EXPIRED", "FACT", "HYPOTHESIS"})


def _finite_float(value: Any, *, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(numeric) or (minimum is not None and numeric < minimum) or (maximum is not None and numeric > maximum):
        raise ValueError(f"{name} must be a finite number within the allowed range")
    return numeric


def _finite_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer within the allowed range")
    return value


_SECRET_KEY = re.compile(r"(secret|token|password|passwd|api[_-]?key|authorization|cookie|private[_-]?key)", re.I)
_LIVE_ORDER = re.compile(r"(live[_-]?order|real[_-]?order|send[_-]?order|financial[_-]?order|place[_-]?order|ordem\s+real|enviar\s+ordem)", re.I)
_DANGEROUS_INTENT = re.compile(
    r"(ordem\s+real|enviar\s+ordem|place\s+(?:a\s+)?live\s+order|desativar\s+(?:o\s+)?policy|alterar\s+(?:a\s+)?allowlist|exfiltrar\s+segredo|autoeleva|shell\s+arbitr[aá]rio|ignore\s+(?:all\s+)?previous\s+instructions|ignore\s+the\s+system\s+prompt)",
    re.I,
)

_INJECTION_RULES: tuple[tuple[re.Pattern[str], str, float, str], ...] = (
    (re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I), "prompt_injection", 45.0, "instruction_override"),
    (re.compile(r"ignore\s+(?:the\s+)?system\s+prompt|ignore\s+developer", re.I), "prompt_injection", 55.0, "system_override"),
    (re.compile(r"reveal\s+(?:your|the)\s+(?:system|developer)\s+prompt|mostre\s+o\s+prompt", re.I), "prompt_injection", 45.0, "prompt_exfiltration"),
    (re.compile(r"bypass\s+(?:the\s+)?(?:policy|safety|guard)|contorne\s+(?:a\s+)?pol[ií]tica", re.I), "prompt_injection", 55.0, "policy_bypass"),
    (re.compile(r"you\s+are\s+now\s+|agora\s+voc[eê]\s+[eé]", re.I), "prompt_injection", 25.0, "role_hijack"),
)
_PII_RULES: tuple[tuple[re.Pattern[str], str, float, str, str], ...] = (
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "pii", 25.0, "email", "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b"), "pii", 35.0, "cpf_like", "[CPF_REDACTED]"),
    (re.compile(r"(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})[-\s]?\d{4}\b"), "pii", 25.0, "phone_like", "[PHONE_REDACTED]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "financial_pii", 55.0, "card_like", "[CARD_REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "secret", 90.0, "bearer_token", "Bearer [TOKEN_REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "secret", 90.0, "provider_key", "[API_KEY_REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "secret", 90.0, "aws_access_key", "[AWS_KEY_REDACTED]"),
    (re.compile(r"(?i)\b(?:password|senha|token|api[_-]?key)\s*[:=]\s*[^\s,;]+"), "secret", 85.0, "credential_assignment", "[SECRET_REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "secret", 100.0, "private_key_header", "[PRIVATE_KEY_REDACTED]"),
)
_SCOPE_RULES: tuple[tuple[re.Pattern[str], str, float, str], ...] = (
    (re.compile(r"\b(?:powershell|cmd\.exe|subprocess|os\.system|run_command|shell)\b", re.I), "scope_violation", 85.0, "arbitrary_execution"),
    (re.compile(r"\b(?:delete|drop\s+table|format\s+disk|kill\s+process|desativar|apagar\s+logs?)\b", re.I), "scope_violation", 75.0, "destructive_operation"),
    (_LIVE_ORDER, "prohibited_action", 100.0, "live_financial_order"),
    (re.compile(r"\b(?:credential|api[_-]?key|access[_-]?token|senha|segredo)\b", re.I), "scope_violation", 80.0, "secret_access"),
)


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    PROHIBITED = "PROHIBITED"


class AutonomyMode(str, Enum):
    OBSERVE = "OBSERVE"
    PLAN_ONLY = "PLAN_ONLY"
    DRY_RUN = "DRY_RUN"
    SUPERVISED = "SUPERVISED"
    GUARDED_AUTONOMY = "GUARDED_AUTONOMY"
    DISABLED = "DISABLED"


class DecisionStatus(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class RiskFinding:
    category: str
    rule: str
    score: float
    evidence: str
    direction: str


@dataclass(frozen=True)
class RiskReport:
    is_safe: bool
    score: float
    threshold: float
    categories: tuple[str, ...]
    findings: tuple[RiskFinding, ...]
    scope_ok: bool
    redacted_text: str
    trace_id: str
    direction: str
    latency_ms: float


class PolicyViolation(RuntimeError):
    def __init__(self, report: RiskReport) -> None:
        super().__init__(f"policy blocked {report.direction}: score={report.score:.2f}, categories={report.categories}")
        self.report = report


class EventHandler(Protocol):
    def __call__(self, event: Mapping[str, Any]) -> None: ...


class EventBus:
    """Small synchronous event bus; subscriber failures never break the caller."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if not event_type or not callable(handler):
            raise ValueError("event_type and callable handler are required")
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event_type: str, *, trace_id: str, payload: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        event = {"event_type": event_type, "trace_id": trace_id, "created_at": datetime.now(timezone.utc).isoformat(), "payload": sanitize(payload or {})}
        with self._lock:
            handlers = tuple(self._handlers.get(event_type, ())) + tuple(self._handlers.get("*", ()))
        errors: list[str] = []
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                errors.append(type(exc).__name__)
        return tuple(errors)


class SemanticRiskClassifier(Protocol):
    def score(self, text: str, *, direction: str) -> float: ...


class RiskAnalyzer:
    """Deterministic lexical/semantic heuristic scorer with an optional classifier.

    The built-in scorer is intentionally conservative and explainable. A real
    embedding or classifier can be injected through ``semantic_classifier``;
    its score is capped and remains subject to the hard safety rules.
    """

    def __init__(self, *, threshold: float = 70.0, semantic_classifier: SemanticRiskClassifier | None = None) -> None:
        numeric_threshold = _finite_float(threshold, name="risk threshold", minimum=0.0, maximum=100.0)
        if numeric_threshold <= 0:
            raise ValueError("risk threshold must be between 0 and 100")
        self.threshold = numeric_threshold
        self.semantic_classifier = semantic_classifier

    @staticmethod
    def redact(text: str) -> str:
        original = str(text)[:MAX_TEXT]
        candidates: list[tuple[int, int, str]] = []
        for pattern, _category, _score, _rule, replacement in _PII_RULES:
            candidates.extend((match.start(), match.end(), replacement) for match in pattern.finditer(original))
        selected: list[tuple[int, int, str]] = []
        for start, end, replacement in sorted(candidates, key=lambda item: (item[1] - item[0], item[0])):
            if any(start < selected_end and end > selected_start for selected_start, selected_end, _ in selected):
                continue
            selected.append((start, end, replacement))
        for start, end, replacement in sorted(selected, key=lambda item: item[0], reverse=True):
            original = original[:start] + replacement + original[end:]
        return original

    def analyze(
        self,
        text: str,
        *,
        direction: Literal["prompt", "response", "tool_request", "tool_output"] = "prompt",
        trace_id: str | None = None,
        allowed_scope: Sequence[str] | None = None,
    ) -> RiskReport:
        started = time.perf_counter()
        trace_id = trace_id or str(uuid.uuid4())
        raw = str(text)[:MAX_TEXT]
        findings: list[RiskFinding] = []
        normalized = raw.lower()
        for pattern, category, score, rule in _INJECTION_RULES:
            match = pattern.search(raw)
            if match:
                findings.append(RiskFinding(category, rule, score, match.group(0)[:160], direction))
        for pattern, category, score, rule, _replacement in _PII_RULES:
            match = pattern.search(raw)
            if match:
                findings.append(RiskFinding(category, rule, score, self.redact(match.group(0)[:120]), direction))
        for pattern, category, score, rule in _SCOPE_RULES:
            match = pattern.search(raw)
            if match:
                findings.append(RiskFinding(category, rule, score, match.group(0)[:160], direction))
        if any(term in normalized for term in ("ignore", "ignora")) and any(term in normalized for term in ("policy", "política", "instructions", "instruções")):
            findings.append(RiskFinding("semantic_injection", "override_intent_proximity", 25.0, "override terms in same context", direction))
        if self.semantic_classifier is not None:
            try:
                semantic_score = _finite_float(self.semantic_classifier.score(raw, direction=direction), name="semantic classifier score")
                if semantic_score > 0:
                    findings.append(RiskFinding("semantic_risk", "injected_classifier", min(100.0, semantic_score), "classifier_signal", direction))
            except Exception:
                findings.append(RiskFinding("semantic_risk", "classifier_unavailable", 5.0, "classifier failure treated as warning", direction))
        if allowed_scope:
            if isinstance(allowed_scope, str) or not isinstance(allowed_scope, Sequence):
                raise ValueError("allowed_scope must be a sequence of non-empty strings")
            normalized_scope: list[str] = []
            for item in allowed_scope:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("allowed_scope must be a sequence of non-empty strings")
                normalized_scope.append(item.strip().lower())
            if normalized_scope and not any(term in normalized for term in normalized_scope):
                findings.append(RiskFinding("scope_violation", "outside_declared_scope", 25.0, "no declared scope term matched", direction))
        score = min(100.0, sum(item.score for item in findings))
        categories = tuple(sorted({item.category for item in findings}))
        scope_violation = any(item.category == "scope_violation" for item in findings)
        hard_block = any(item.category in {"prompt_injection", "semantic_injection", "prohibited_action"} for item in findings) or bool(_DANGEROUS_INTENT.search(raw)) or (bool(allowed_scope) and scope_violation)
        scope_ok = not any(item.category in {"scope_violation", "prohibited_action"} for item in findings)
        is_safe = score < self.threshold and not hard_block
        return RiskReport(
            is_safe=is_safe,
            score=round(score, 2),
            threshold=self.threshold,
            categories=categories,
            findings=tuple(findings),
            scope_ok=scope_ok,
            redacted_text=self.redact(raw),
            trace_id=trace_id,
            direction=direction,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )


@dataclass(frozen=True)
class ToolManifest:
    name: str
    version: str
    description: str
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    allowed_agents: tuple[str, ...]
    allowed_modes: tuple[AutonomyMode, ...]
    side_effects: tuple[str, ...]
    timeout_s: float
    idempotency: str
    rollback: str
    requires_approval: bool
    audit_events: tuple[str, ...]
    rollback_tool: str | None = None

    def __post_init__(self) -> None:
        timeout = _finite_float(self.timeout_s, name="timeout_s", minimum=0.0, maximum=300.0)
        if timeout <= 0:
            raise ValueError("timeout_s must be positive")
        object.__setattr__(self, "timeout_s", timeout)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolManifest":
        if not isinstance(data, Mapping):
            raise ValueError("manifest must be an object")
        allowed_fields = frozenset({"$schema", "name", "version", "description", "risk_level", "input_schema", "output_schema", "allowed_agents", "allowed_modes", "side_effects", "timeout_s", "idempotency", "rollback", "requires_approval", "audit_events", "rollback_tool"})
        unknown_fields = sorted((key for key in data if key not in allowed_fields), key=repr)
        if unknown_fields:
            raise ValueError(f"manifest contains unknown fields: {unknown_fields}")

        def required_string(key: str) -> str:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"manifest field {key!r} must be a non-empty string")
            return value.strip()

        name = required_string("name")
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", name):
            raise ValueError("manifest name must be lowercase snake_case")
        try:
            risk_level = RiskLevel(data.get("risk_level"))
            modes = tuple(AutonomyMode(item) for item in data.get("allowed_modes", []))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid risk_level or allowed_modes") from exc
        if not modes:
            raise ValueError("allowed_modes cannot be empty")
        agents = data.get("allowed_agents")
        if not isinstance(agents, list) or not agents or not all(isinstance(item, str) and item.strip() for item in agents):
            raise ValueError("allowed_agents must be a non-empty string array")
        side_effects = data.get("side_effects")
        if not isinstance(side_effects, list) or not all(isinstance(item, str) and item.strip() for item in side_effects):
            raise ValueError("side_effects must be a string array")
        audit_events = data.get("audit_events")
        if not isinstance(audit_events, list) or not audit_events or not all(isinstance(item, str) and item.strip() for item in audit_events):
            raise ValueError("audit_events must be a non-empty string array")
        timeout_s = data.get("timeout_s")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= 300:
            raise ValueError("timeout_s must be between 0 and 300 seconds")
        for schema_name in ("input_schema", "output_schema"):
            schema = data.get(schema_name)
            if not isinstance(schema, dict) or schema.get("type") != "object" or not isinstance(schema.get("properties"), dict) or not isinstance(schema.get("required"), list) or schema.get("additionalProperties") is not False:
                raise ValueError(f"{schema_name} must be an object schema with explicit members and additionalProperties=false")
            properties = schema["properties"]
            required = schema["required"]
            if not all(isinstance(key, str) and key for key in properties) or not all(isinstance(key, str) and key for key in required) or not set(required).issubset(properties):
                raise ValueError(f"{schema_name} contains invalid required or property keys")
        idempotency = required_string("idempotency")
        if idempotency not in {"idempotent", "keyed", "non_idempotent"}:
            raise ValueError("invalid idempotency")
        approval = data.get("requires_approval")
        if not isinstance(approval, bool):
            raise ValueError("requires_approval must be boolean")
        rollback_tool = data.get("rollback_tool")
        if rollback_tool is not None and (not isinstance(rollback_tool, str) or not rollback_tool.strip()):
            raise ValueError("rollback_tool must be a non-empty string or null")
        if risk_level is RiskLevel.PROHIBITED:
            approval = True
        return cls(
            name=name,
            version=required_string("version"),
            description=required_string("description"),
            risk_level=risk_level,
            input_schema=dict(data["input_schema"]),
            output_schema=dict(data["output_schema"]),
            allowed_agents=tuple(agents),
            allowed_modes=modes,
            side_effects=tuple(side_effects),
            timeout_s=float(timeout_s),
            idempotency=idempotency,
            rollback=required_string("rollback"),
            requires_approval=approval,
            audit_events=tuple(audit_events),
            rollback_tool=rollback_tool.strip() if isinstance(rollback_tool, str) else None,
        )

    def fingerprint(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "risk_level": self.risk_level.value,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "allowed_agents": self.allowed_agents,
            "allowed_modes": [item.value for item in self.allowed_modes],
            "side_effects": self.side_effects,
            "timeout_s": self.timeout_s,
            "idempotency": self.idempotency,
            "rollback": self.rollback,
            "requires_approval": self.requires_approval,
            "audit_events": self.audit_events,
            "rollback_tool": self.rollback_tool,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ToolRegistry:
    def __init__(self, manifests: list[ToolManifest] | None = None) -> None:
        self._manifests: dict[str, ToolManifest] = {}
        self._fingerprints: dict[str, str] = {}
        for manifest in manifests or []:
            self.register(manifest)

    def register(self, manifest: ToolManifest) -> None:
        if not isinstance(manifest, ToolManifest):
            raise TypeError("manifest must be a ToolManifest")
        if manifest.name in self._manifests:
            raise ValueError(f"duplicate tool manifest: {manifest.name}")
        self._manifests[manifest.name] = manifest
        self._fingerprints[manifest.name] = manifest.fingerprint()

    def get(self, name: str) -> ToolManifest | None:
        return self._manifests.get(name)

    def integrity_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        for name, manifest in self._manifests.items():
            try:
                if manifest.fingerprint() != self._fingerprints.get(name):
                    errors.append(f"manifest mutated: {name}")
            except Exception:
                errors.append(f"manifest unreadable: {name}")
        return tuple(errors)

    def integrity_ok(self) -> bool:
        return not self.integrity_errors()

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._manifests))


@dataclass(frozen=True)
class PerformanceMetric:
    trace_id: str
    stage: str
    status: str
    duration_ms: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    status: DecisionStatus
    tool: str
    risk_level: RiskLevel | None
    reason: str
    trace_id: str
    required_approval: bool = False
    schema_errors: tuple[str, ...] = ()
    risk_report: RiskReport | None = None
    audit_status: str = "NOT_ATTEMPTED"
    audit_error: str | None = None


def _validate_value(value: Any, schema: Mapping[str, Any], path: str = "$", *, depth: int = 0) -> list[str]:
    errors: list[str] = []
    if depth > MAX_SCHEMA_DEPTH:
        return [f"{path}: schema value exceeds maximum depth"]
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return [f"{path}: properties must be an object"]
        if len(value) > MAX_MAPPING_ITEMS:
            errors.append(f"{path}: object exceeds maximum property count")
        required = schema.get("required", [])
        if not isinstance(required, list):
            errors.append(f"{path}: required must be an array")
            required = []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required field missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional property rejected")
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                errors.extend(_validate_value(value[key], child_schema, f"{path}.{key}", depth=depth + 1))
    elif schema_type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
        else:
            if len(value) > MAX_SCHEMA_ITEMS:
                errors.append(f"{path}: array exceeds maximum item count")
            min_items = schema.get("minItems")
            max_items = schema.get("maxItems")
            if isinstance(min_items, int) and len(value) < min_items:
                errors.append(f"{path}: fewer than minItems")
            if isinstance(max_items, int) and len(value) > max_items:
                errors.append(f"{path}: more than maxItems")
            if isinstance(schema.get("items"), dict):
                for index, item in enumerate(value):
                    errors.extend(_validate_value(item, schema["items"], f"{path}[{index}]", depth=depth + 1))
    elif schema_type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
        else:
            if len(value) > MAX_TEXT:
                errors.append(f"{path}: string exceeds maximum length")
            if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than minLength")
            if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than maxLength")
    elif schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: expected integer")
    elif schema_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: expected number")
        elif isinstance(value, float) and not math.isfinite(value):
            errors.append(f"{path}: non-finite number rejected")
    elif schema_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
    elif schema_type is not None:
        errors.append(f"{path}: unsupported schema type {schema_type!r}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path}: value outside enum")
    return errors


class ToolRiskValidator:
    """Validate allowlists, modes, schemas and deterministic risk policy."""

    def evaluate(
        self,
        manifest: ToolManifest,
        arguments: Mapping[str, Any],
        *,
        agent: str,
        mode: AutonomyMode,
        trace_id: str,
        approval_granted: bool = False,
        risk_report: RiskReport | None = None,
        for_planning: bool = False,
    ) -> PolicyDecision:
        if not isinstance(approval_granted, bool):
            approval_granted = False
        if agent not in manifest.allowed_agents:
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "agent is not allowlisted", trace_id, risk_report=risk_report)
        if mode not in manifest.allowed_modes and not (for_planning and mode in {AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DRY_RUN}):
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "autonomy mode is not allowed", trace_id, risk_report=risk_report)
        if not isinstance(arguments, Mapping):
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "arguments must be an object", trace_id, risk_report=risk_report)
        schema_errors = tuple(_validate_value(dict(arguments), manifest.input_schema))
        if schema_errors:
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "arguments violate tool schema", trace_id, schema_errors=schema_errors, risk_report=risk_report)
        if manifest.risk_level is RiskLevel.PROHIBITED or _LIVE_ORDER.search(manifest.name) or any(_LIVE_ORDER.search(item) for item in manifest.side_effects):
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "prohibited live-order or financial side effect", trace_id, risk_report=risk_report)
        if not for_planning and mode in {AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DISABLED} and manifest.side_effects:
            return PolicyDecision(DecisionStatus.DENY, manifest.name, manifest.risk_level, "current mode does not permit side effects", trace_id, risk_report=risk_report)
        needs_approval = manifest.requires_approval or manifest.risk_level is RiskLevel.HIGH or bool(manifest.side_effects)
        if needs_approval and not approval_granted:
            return PolicyDecision(DecisionStatus.REQUIRE_APPROVAL, manifest.name, manifest.risk_level, "explicit approval required before tool execution", trace_id, required_approval=True, risk_report=risk_report)
        return PolicyDecision(DecisionStatus.ALLOW, manifest.name, manifest.risk_level, "tool request satisfies policy", trace_id, risk_report=risk_report)


class ApprovalValidator(Protocol):
    def validate(self, grant: Any, *, task_id: str, trace_id: str, tool: str, arguments: Mapping[str, Any], mode: str, now: float | None = None, consume: bool = False) -> bool: ...


class PolicyGate:
    """Single policy boundary for prompts, responses and tool requests."""

    def __init__(
        self,
        registry: ToolRegistry,
        validator: ToolRiskValidator | None = None,
        *,
        risk_analyzer: RiskAnalyzer | None = None,
        audit_ledger: Any | None = None,
        event_bus: EventBus | None = None,
        approval_validator: ApprovalValidator | None = None,
    ) -> None:
        self.registry = registry
        self.validator = validator or ToolRiskValidator()
        self.risk_analyzer = risk_analyzer or RiskAnalyzer()
        self.audit_ledger = audit_ledger
        self.event_bus = event_bus
        self.approval_validator = approval_validator
        # Instâncias unitárias não presumem um teto; o Admin API de produção
        # carrega o teto real de config/aura-admin-config.json explicitamente.
        self._mode_ceiling: AutonomyMode | None = None
    @property
    def mode_ceiling(self) -> AutonomyMode | None:
        return self._mode_ceiling


    def set_mode_ceiling(self, mode: AutonomyMode) -> None:
        if not isinstance(mode, AutonomyMode):
            raise ValueError("mode ceiling must be an AutonomyMode")
        self._mode_ceiling = mode

    def inspect_prompt(self, prompt: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.risk_analyzer.analyze(prompt, direction="prompt", trace_id=trace_id, allowed_scope=allowed_scope)

    def inspect_response(self, response: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.risk_analyzer.analyze(response, direction="response", trace_id=trace_id, allowed_scope=allowed_scope)

    def intercept_prompt(self, prompt: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.inspect_prompt(prompt, trace_id=trace_id, allowed_scope=allowed_scope)

    def intercept_response(self, response: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.inspect_response(response, trace_id=trace_id, allowed_scope=allowed_scope)

    def enforce_prompt(self, prompt: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        report = self.inspect_prompt(prompt, trace_id=trace_id, allowed_scope=allowed_scope)
        if not report.is_safe:
            self._publish("policy_blocked", report.trace_id, {"direction": report.direction, "score": report.score, "categories": report.categories})
            raise PolicyViolation(report)
        return report

    def enforce_response(self, response: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        report = self.inspect_response(response, trace_id=trace_id, allowed_scope=allowed_scope)
        if not report.is_safe:
            self._publish("policy_blocked", report.trace_id, {"direction": report.direction, "score": report.score, "categories": report.categories})
            raise PolicyViolation(report)
        return report

    def decide(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        agent: str,
        mode: AutonomyMode,
        trace_id: str | None = None,
        approval_granted: bool = False,
        approval: Any | None = None,
        task_id: str | None = None,
        for_planning: bool = False,
    ) -> PolicyDecision:
        trace_id = trace_id or str(uuid.uuid4())
        if not isinstance(mode, AutonomyMode):
            decision = PolicyDecision(DecisionStatus.DENY, tool, None, "invalid autonomy mode", trace_id)
            return self._audit_decision(decision)
        if mode is not AutonomyMode.DISABLED:
            ceiling_rank = {item: index for index, item in enumerate((AutonomyMode.DISABLED, AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DRY_RUN, AutonomyMode.SUPERVISED, AutonomyMode.GUARDED_AUTONOMY))}
            if self._mode_ceiling is not None and ceiling_rank[mode] > ceiling_rank[self._mode_ceiling]:
                decision = PolicyDecision(DecisionStatus.DENY, tool, None, "autonomy mode exceeds configured ceiling", trace_id)
                return self._audit_decision(decision)
        try:
            serialized = json.dumps(arguments, ensure_ascii=False, default=str)
        except (TypeError, ValueError, RecursionError):
            decision = PolicyDecision(DecisionStatus.DENY, tool, None, "tool arguments are not safely serializable", trace_id)
            return self._audit_decision(decision)
        if len(serialized) > MAX_TEXT:
            decision = PolicyDecision(DecisionStatus.DENY, tool, None, "tool arguments exceed maximum serialized size", trace_id)
            return self._audit_decision(decision)
        if not isinstance(approval_granted, bool):
            approval_granted = False
        risk_report = self.risk_analyzer.analyze(serialized, direction="tool_request", trace_id=trace_id)
        if not risk_report.is_safe:
            decision = PolicyDecision(DecisionStatus.DENY, tool, None, "risk analyzer blocked tool request", trace_id, risk_report=risk_report)
            return self._audit_decision(decision)
        if approval is not None:
            approval_granted = False
            if self.approval_validator is not None and task_id:
                try:
                    validated_approval = self.approval_validator.validate(approval, task_id=task_id, trace_id=trace_id, tool=tool, arguments=arguments, mode=mode.value)
                    approval_granted = validated_approval is True
                except Exception:
                    approval_granted = False
        if not self.registry.integrity_ok():
            return PolicyDecision(DecisionStatus.DENY, tool, None, "tool registry integrity check failed", trace_id)
        manifest = self.registry.get(tool)
        if manifest is None:
            decision = PolicyDecision(DecisionStatus.DENY, tool, None, "tool is not registered", trace_id, risk_report=risk_report)
            return self._audit_decision(decision)
        decision = self.validator.evaluate(manifest, arguments, agent=agent, mode=mode, trace_id=trace_id, approval_granted=approval_granted, risk_report=risk_report, for_planning=for_planning)
        return self._audit_decision(decision)

    def _publish(self, event_type: str, trace_id: str, payload: Mapping[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(event_type, trace_id=trace_id, payload=payload)

    def _audit_decision(self, decision: PolicyDecision) -> PolicyDecision:
        self._publish("policy_decision", decision.trace_id, {"tool": decision.tool, "status": decision.status.value, "reason": decision.reason})
        if self.audit_ledger is None:
            return decision
        try:
            self.audit_ledger.append_event(
                trace_id=decision.trace_id,
                task_id=None,
                event_type="policy_decision",
                actor="PolicyGate",
                status=decision.status.value,
                payload={
                    "tool": decision.tool,
                    "risk_level": decision.risk_level.value if decision.risk_level else None,
                    "reason": decision.reason,
                    "required_approval": decision.required_approval,
                    "schema_errors": decision.schema_errors,
                    "risk_score": decision.risk_report.score if decision.risk_report else None,
                },
                idempotency_key=f"{decision.trace_id}:policy:{decision.tool}:{decision.status.value}",
            )
            if decision.risk_report is not None and hasattr(self.audit_ledger, "record_metric"):
                self.audit_ledger.record_metric(PerformanceMetric(decision.trace_id, "risk_analysis", decision.status.value, decision.risk_report.latency_ms, {"risk_score": decision.risk_report.score}))
            return replace(decision, audit_status="PASS")
        except Exception as exc:
            # Safe reads must not be stopped by an unavailable audit sink. The
            # warning remains visible to the caller and to the final report.
            return replace(decision, audit_status="WARNING", audit_error=type(exc).__name__)


class PolicyInterceptor:
    """Framework-neutral middleware facade for model input and output."""

    def __init__(self, gate: PolicyGate) -> None:
        self.gate = gate

    def before_model(self, prompt: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.gate.enforce_prompt(prompt, trace_id=trace_id, allowed_scope=allowed_scope)

    def after_model(self, response: str, *, trace_id: str | None = None, allowed_scope: Sequence[str] | None = None) -> RiskReport:
        return self.gate.enforce_response(response, trace_id=trace_id, allowed_scope=allowed_scope)


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    tool: str
    arguments: dict[str, Any]
    reason: str
    risk_level: RiskLevel
    requires_approval: bool
    expected: dict[str, Any]
    depends_on: tuple[str, ...] = ()
    rollback_tool: str | None = None
    rollback_arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdminPlan:
    task_id: str
    goal: str
    assumptions: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    stop_conditions: tuple[str, ...]
    evidence_requirements: tuple[str, ...]
    execution_order: tuple[str, ...] = ()
    rollback_order: tuple[str, ...] = ()

    def fingerprint(self) -> str:
        payload = {
            "task_id": self.task_id,
            "goal": self.goal,
            "assumptions": self.assumptions,
            "steps": [{"step_id": step.step_id, "tool": step.tool, "arguments": step.arguments, "reason": step.reason, "risk_level": step.risk_level.value, "requires_approval": step.requires_approval, "expected": step.expected, "depends_on": step.depends_on, "rollback_tool": step.rollback_tool, "rollback_arguments": step.rollback_arguments} for step in self.steps],
            "stop_conditions": self.stop_conditions,
            "evidence_requirements": self.evidence_requirements,
            "execution_order": self.execution_order,
            "rollback_order": self.rollback_order,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PlanVerification:
    valid: bool
    plan: AdminPlan | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    required_approvals: tuple[str, ...]
    execution_order: tuple[str, ...] = ()
    rollback_order: tuple[str, ...] = ()


class PlanInvariantChecker(Protocol):
    def __call__(self, step: Mapping[str, Any], *, agent: str, mode: AutonomyMode) -> Sequence[str]: ...


class PlanVerifier:
    def __init__(self, policy_gate: PolicyGate, max_steps: int = MAX_PLAN_STEPS, invariant_checker: PlanInvariantChecker | None = None) -> None:
        self.policy_gate = policy_gate
        self.max_steps = _finite_int(max_steps, name="max_steps", minimum=1, maximum=MAX_PLAN_STEPS)
        self.invariant_checker = invariant_checker

    @staticmethod
    def _topological_order(steps: Sequence[PlanStep]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        by_id = {step.step_id: step for step in steps}
        indegree = {step.step_id: 0 for step in steps}
        successors: dict[str, list[str]] = {step.step_id: [] for step in steps}
        for step in steps:
            for dependency in step.depends_on:
                if dependency in by_id:
                    indegree[step.step_id] += 1
                    successors[dependency].append(step.step_id)
        ready = [step.step_id for step in steps if indegree[step.step_id] == 0]
        order: list[str] = []
        while ready:
            current = ready.pop(0)
            order.append(current)
            for successor in successors[current]:
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
        if len(order) != len(steps):
            return (), ()
        return tuple(order), tuple(reversed(order))

    def verify_document(self, document: str | bytes | Mapping[str, Any], *, agent: str, mode: AutonomyMode, trace_id: str | None = None) -> PlanVerification:
        try:
            data = load_structured_document(document)
        except ValueError as exc:
            return PlanVerification(False, None, (str(exc),), (), ())
        return self.verify(data, agent=agent, mode=mode, trace_id=trace_id)

    def verify(self, data: Mapping[str, Any], *, agent: str, mode: AutonomyMode, trace_id: str | None = None) -> PlanVerification:
        errors: list[str] = []
        warnings: list[str] = []
        approvals: list[str] = []
        if not isinstance(data, Mapping):
            return PlanVerification(False, None, ("plan must be an object",), (), ())
        allowed_keys = {"task_id", "goal", "assumptions", "steps", "stop_conditions", "evidence_requirements"}
        unknown_keys = set(data) - allowed_keys
        if unknown_keys:
            errors.append(f"unknown top-level fields: {sorted(unknown_keys)}")
        task_id = data.get("task_id")
        goal = data.get("goal")
        if not isinstance(task_id, str) or not task_id.strip():
            errors.append("task_id must be a non-empty string")
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2_000:
            errors.append("goal must be a non-empty string of at most 2000 characters")
        elif _DANGEROUS_INTENT.search(goal):
            errors.append("goal contains prohibited administrative intent")
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            errors.append("steps must be a non-empty array")
            raw_steps = []
        elif len(raw_steps) > self.max_steps:
            errors.append(f"steps exceed maximum of {self.max_steps}")
        stop_conditions = data.get("stop_conditions")
        evidence_requirements = data.get("evidence_requirements")
        if not isinstance(stop_conditions, list) or not stop_conditions or not all(isinstance(item, str) and item.strip() for item in stop_conditions):
            errors.append("stop_conditions must be a non-empty string array")
            stop_conditions = []
        if not isinstance(evidence_requirements, list) or not evidence_requirements or not all(isinstance(item, str) and item.strip() for item in evidence_requirements):
            errors.append("evidence_requirements must be a non-empty string array")
            evidence_requirements = []
        assumptions = data.get("assumptions", [])
        if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
            errors.append("assumptions must be a string array")
            assumptions = []

        plan_steps: list[PlanStep] = []
        seen_ids: set[str] = set()
        trace_id = trace_id or str(uuid.uuid4())
        allowed_step_keys = {"step_id", "tool", "arguments", "reason", "risk_level", "requires_approval", "expected", "depends_on", "rollback_tool", "rollback_arguments"}
        for index, raw in enumerate(raw_steps):
            prefix = f"steps[{index}]"
            if not isinstance(raw, Mapping):
                errors.append(f"{prefix}: must be an object")
                continue
            unknown_step_keys = set(raw) - allowed_step_keys
            if unknown_step_keys:
                errors.append(f"{prefix}: unknown fields: {sorted(unknown_step_keys)}")
            step_id = raw.get("step_id")
            tool = raw.get("tool")
            arguments = raw.get("arguments")
            reason = raw.get("reason", "")
            expected = raw.get("expected", {})
            declared_risk = raw.get("risk_level")
            requires_approval = raw.get("requires_approval")
            depends_on = raw.get("depends_on", [])
            rollback_tool = raw.get("rollback_tool")
            rollback_arguments = raw.get("rollback_arguments", {})
            if not isinstance(step_id, str) or not re.fullmatch(r"s[0-9]+", step_id):
                errors.append(f"{prefix}.step_id: expected s<number>")
                continue
            if step_id in seen_ids:
                errors.append(f"{prefix}.step_id: duplicate step id")
            seen_ids.add(step_id)
            if not isinstance(tool, str) or not tool:
                errors.append(f"{prefix}.tool: non-empty string required")
                continue
            if not isinstance(arguments, dict):
                errors.append(f"{prefix}.arguments: object required")
                arguments = {}
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{prefix}.reason: non-empty string required")
                reason = ""
            if not isinstance(expected, dict):
                errors.append(f"{prefix}.expected: object required")
                expected = {}
            try:
                risk_level = RiskLevel(declared_risk)
            except (TypeError, ValueError):
                errors.append(f"{prefix}.risk_level: invalid risk level")
                risk_level = RiskLevel.PROHIBITED
            if not isinstance(requires_approval, bool):
                errors.append(f"{prefix}.requires_approval: boolean required")
                requires_approval = True
            if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
                errors.append(f"{prefix}.depends_on: string array required")
                depends_on = []
            if rollback_tool is not None and (not isinstance(rollback_tool, str) or not rollback_tool.strip()):
                errors.append(f"{prefix}.rollback_tool: non-empty string or null required")
                rollback_tool = None
            if not isinstance(rollback_arguments, dict):
                errors.append(f"{prefix}.rollback_arguments: object required")
                rollback_arguments = {}
            if _DANGEROUS_INTENT.search(tool) or _DANGEROUS_INTENT.search(json.dumps(arguments, ensure_ascii=False)):
                errors.append(f"{prefix}: prohibited intent in tool or arguments")
            if self.invariant_checker is not None:
                try:
                    invariant_errors = tuple(str(item) for item in self.invariant_checker(raw, agent=agent, mode=mode) if str(item).strip())
                    errors.extend(f"{prefix}: invariant violation: {item}" for item in invariant_errors)
                except Exception as exc:
                    errors.append(f"{prefix}: invariant checker failed: {type(exc).__name__}")
            decision = self.policy_gate.decide(tool, arguments, agent=agent, mode=mode, trace_id=trace_id, approval_granted=False, for_planning=True)
            if decision.status is DecisionStatus.DENY:
                errors.append(f"{prefix}: policy denied: {decision.reason}")
            elif decision.status is DecisionStatus.REQUIRE_APPROVAL:
                approvals.append(step_id)
                if not requires_approval:
                    errors.append(f"{prefix}: approval flag must be true for this risk")
            if decision.risk_level is not None and risk_level is not decision.risk_level:
                errors.append(f"{prefix}: declared risk does not match manifest")
            manifest = self.policy_gate.registry.get(tool)
            effective_rollback_tool = rollback_tool or (manifest.rollback_tool if manifest else None)
            if manifest and manifest.side_effects and not effective_rollback_tool:
                errors.append(f"{prefix}: side-effecting step requires rollback_tool")
            if effective_rollback_tool:
                rollback_manifest = self.policy_gate.registry.get(effective_rollback_tool)
                if rollback_manifest is None:
                    errors.append(f"{prefix}: rollback tool is not registered")
                else:
                    rollback_decision = self.policy_gate.decide(effective_rollback_tool, rollback_arguments, agent=agent, mode=mode, trace_id=trace_id, approval_granted=False, for_planning=True)
                    if rollback_decision.status is DecisionStatus.DENY:
                        errors.append(f"{prefix}: rollback policy denied: {rollback_decision.reason}")
                    elif rollback_decision.status is DecisionStatus.REQUIRE_APPROVAL:
                        approvals.append(step_id)
                        if not requires_approval:
                            errors.append(f"{prefix}: rollback requires approval but step flag is false")
            plan_steps.append(PlanStep(step_id, tool, dict(arguments), reason, risk_level, requires_approval, dict(expected), tuple(depends_on), effective_rollback_tool, dict(rollback_arguments)))

        ordered_ids = {step.step_id for step in plan_steps}
        for step in plan_steps:
            unknown = set(step.depends_on) - ordered_ids
            if unknown:
                errors.append(f"{step.step_id}: unknown dependencies: {sorted(unknown)}")
            if step.step_id in step.depends_on:
                errors.append(f"{step.step_id}: self dependency")
        if len({step.step_id for step in plan_steps}) != len(plan_steps):
            errors.append("step ids must be unique")
        if any(item.strip().lower() in {"loop forever", "retry forever", "until success without limit"} for item in stop_conditions):
            errors.append("unbounded stop condition")
        execution_order, rollback_order = self._topological_order(plan_steps)
        if plan_steps and not execution_order:
            errors.append("dependency graph contains a cycle")
        if approvals and mode is AutonomyMode.GUARDED_AUTONOMY:
            warnings.append("plan contains steps that require explicit approval")
        if not plan_steps and raw_steps:
            errors.append("no usable steps remain after validation")

        plan = None
        if not errors:
            plan = AdminPlan(
                task_id=task_id.strip(),
                goal=goal.strip(),
                assumptions=tuple(assumptions),
                steps=tuple(plan_steps),
                stop_conditions=tuple(stop_conditions),
                evidence_requirements=tuple(evidence_requirements),
                execution_order=execution_order,
                rollback_order=rollback_order,
            )
        return PlanVerification(not errors, plan, tuple(errors), tuple(warnings), tuple(sorted(set(approvals))), execution_order, rollback_order)

    @staticmethod
    def schema() -> dict[str, Any]:
        step_properties = {
            "step_id": {"type": "string", "pattern": "^s[0-9]+$"},
            "tool": {"type": "string", "minLength": 1},
            "arguments": {"type": "object", "additionalProperties": True},
            "reason": {"type": "string", "minLength": 1},
            "risk_level": {"type": "string", "enum": [item.value for item in RiskLevel]},
            "requires_approval": {"type": "boolean"},
            "expected": {"type": "object", "additionalProperties": True},
            "depends_on": {"type": "array", "items": {"type": "string"}},
            "rollback_tool": {"type": ["string", "null"]},
            "rollback_arguments": {"type": "object", "additionalProperties": True},
        }
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1},
                "goal": {"type": "string", "minLength": 1, "maxLength": 2000},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "steps": {"type": "array", "minItems": 1, "maxItems": MAX_PLAN_STEPS, "items": {"type": "object", "properties": step_properties, "additionalProperties": False}},
                "stop_conditions": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "evidence_requirements": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            },
            "required": ["task_id", "goal", "steps", "stop_conditions", "evidence_requirements"],
            "additionalProperties": False,
        }


class StructuredModelAdapter(Protocol):
    def complete(self, *, messages: list[dict[str, Any]], response_schema: dict[str, Any], timeout_s: float) -> str | Mapping[str, Any]: ...


@dataclass(frozen=True)
class PlannerResult:
    status: str
    trace_id: str
    verification: PlanVerification
    error_code: str | None = None
    latency_ms: float = 0.0


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[depth-limited]"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= MAX_MAPPING_ITEMS:
                break
            normalized_key = str(key)
            result[normalized_key] = "[REDACTED]" if _SECRET_KEY.search(normalized_key) else sanitize(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth=depth + 1) for item in list(value)[:200]]
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_TEXT]


def load_structured_document(document: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(document, Mapping):
        return dict(document)
    if isinstance(document, bytes):
        document = document.decode("utf-8")
    if not isinstance(document, str) or not document.strip():
        raise ValueError("plan document must be non-empty JSON/YAML text or object")
    text = document.strip()
    if len(text) > MAX_PLAN_DOCUMENT_CHARS:
        raise ValueError("plan document exceeds maximum size")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError("YAML support unavailable; install PyYAML or use JSON") from exc
        try:
            data = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"invalid YAML plan: {type(exc).__name__}") from exc
    if not isinstance(data, Mapping):
        raise ValueError("structured plan root must be an object")
    return dict(data)


class GLMPlanner:
    def __init__(self, adapter: StructuredModelAdapter, verifier: PlanVerifier, *, timeout_s: float = 30.0, audit_ledger: Any | None = None, request_risk_analyzer: RiskAnalyzer | None = None, max_context_chars: int = 32_000) -> None:
        planner_timeout = _finite_float(timeout_s, name="timeout_s", minimum=0.0, maximum=300.0)
        if planner_timeout <= 0:
            raise ValueError("timeout_s must be positive")
        planner_context_limit = _finite_int(max_context_chars, name="max_context_chars", minimum=1_000, maximum=128_000)
        self.adapter = adapter
        self.verifier = verifier
        self.timeout_s = planner_timeout
        self.audit_ledger = audit_ledger
        self.request_risk_analyzer = request_risk_analyzer or RiskAnalyzer()
        self.max_context_chars = planner_context_limit

    def _record_latency(self, trace_id: str, status: str, started: float, metadata: Mapping[str, Any] | None = None) -> float:
        duration_ms = _elapsed_ms(started)
        if self.audit_ledger is not None and hasattr(self.audit_ledger, "record_metric"):
            try:
                self.audit_ledger.record_metric(PerformanceMetric(trace_id, "glm_planning", status, duration_ms, metadata or {}))
            except Exception:
                pass
        return duration_ms

    def build_messages(self, *, task_id: str, goal: str, context: Mapping[str, Any], mode: AutonomyMode) -> list[dict[str, Any]]:
        context_json = json.dumps(sanitize(context), ensure_ascii=False, separators=(",", ":"))
        if len(context_json) > self.max_context_chars:
            raise ValueError("planner context exceeds max_context_chars")
        return [
            {
                "role": "system",
                "content": (
                    "Você é o GLMPlanner do AURA Quant-X. Produza somente um plano JSON conforme o schema. "
                    "Você não executa ferramentas, não altera políticas, não acessa shell/banco diretamente, "
                    "não cria ordem real e não pode mudar allowlist, credenciais ou PAPER TRADE. "
                    f"Modo atual: {mode.value}. Inclua dependências DAG, rollback_tool para efeitos colaterais, "
                    "stop_conditions e evidence_requirements."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"task_id": task_id, "goal": goal, "context": context_json, "mode": mode.value}, ensure_ascii=False),
            },
        ]

    def plan(self, *, task_id: str, goal: str, context: Mapping[str, Any], agent: str, mode: AutonomyMode, trace_id: str | None = None) -> PlannerResult:
        started = time.perf_counter()
        trace_id = trace_id or str(uuid.uuid4())
        if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 256:
            verification = PlanVerification(False, None, ("task_id must be a non-empty string of at most 256 characters",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "PLANNER_INPUT_REJECTED"})
            return PlannerResult("INVALID", trace_id, verification, "PLANNER_INPUT_REJECTED", latency_ms)
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2_000:
            verification = PlanVerification(False, None, ("goal must be a non-empty string of at most 2000 characters",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "PLANNER_INPUT_REJECTED"})
            return PlannerResult("INVALID", trace_id, verification, "PLANNER_INPUT_REJECTED", latency_ms)
        request_report = self.request_risk_analyzer.analyze(goal, direction="prompt", trace_id=trace_id)
        if not request_report.is_safe:
            verification = PlanVerification(False, None, ("request goal blocked by risk policy",), (), ())
            latency_ms = self._record_latency(trace_id, "BLOCKED", started, {"error_code": "REQUEST_RISK_BLOCKED", "risk_score": request_report.score, "risk_categories": request_report.categories})
            return PlannerResult("INVALID", trace_id, verification, "REQUEST_RISK_BLOCKED", latency_ms)
        try:
            messages = self.build_messages(task_id=task_id, goal=goal, context=context, mode=mode)
        except (TypeError, ValueError) as exc:
            verification = PlanVerification(False, None, (f"planner input rejected: {str(exc)}",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "PLANNER_INPUT_REJECTED"})
            return PlannerResult("INVALID", trace_id, verification, "PLANNER_INPUT_REJECTED", latency_ms)
        try:
            raw = self.adapter.complete(messages=messages, response_schema=PlanVerifier.schema(), timeout_s=self.timeout_s)
            data = load_structured_document(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            verification = PlanVerification(False, None, ("GLM response is not valid structured JSON/YAML",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "INVALID_STRUCTURED_OUTPUT"})
            return PlannerResult("INVALID", trace_id, verification, "INVALID_STRUCTURED_OUTPUT", latency_ms)
        except Exception as exc:
            verification = PlanVerification(False, None, (f"GLM adapter failed: {type(exc).__name__}",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "ADAPTER_FAILURE", "exception": type(exc).__name__})
            return PlannerResult("INVALID", trace_id, verification, "ADAPTER_FAILURE", latency_ms)
        if data.get("task_id") != task_id:
            verification = PlanVerification(False, None, ("plan task_id does not match request",), (), ())
            latency_ms = self._record_latency(trace_id, "INVALID", started, {"error_code": "TASK_ID_MISMATCH"})
            return PlannerResult("INVALID", trace_id, verification, "TASK_ID_MISMATCH", latency_ms)
        verification = self.verifier.verify(data, agent=agent, mode=mode, trace_id=trace_id)
        status = "VALID" if verification.valid else "INVALID"
        metadata = {"step_count": len(verification.plan.steps) if verification.plan else 0}
        if verification.plan is not None:
            metadata["plan_fingerprint"] = verification.plan.fingerprint()
            metadata["execution_order"] = verification.execution_order
            metadata["rollback_order"] = verification.rollback_order
        latency_ms = self._record_latency(trace_id, status, started, metadata)
        return PlannerResult(status, trace_id, verification, None if verification.valid else "PLAN_REJECTED", latency_ms)


class PlanExecutionError(RuntimeError):
    pass


class PlanToolExecutor(Protocol):
    def execute(self, step: PlanStep) -> Mapping[str, Any]: ...
    def rollback(self, step: PlanStep, execution_result: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PlanExecutionResult:
    status: Literal["COMPLETED", "BLOCKED", "FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"]
    trace_id: str
    execution_order: tuple[str, ...]
    completed_steps: tuple[str, ...]
    failed_step: str | None
    rollback_completed: tuple[str, ...]
    errors: tuple[str, ...]
    latency_ms: float


class DAGPlanExecutor:
    """Execute only a previously verified plan and rollback completed nodes in reverse order."""

    def __init__(self, policy_gate: PolicyGate, audit_ledger: Any | None = None, event_bus: EventBus | None = None, postcondition_verifier: Any | None = None) -> None:
        self.policy_gate = policy_gate
        self.audit_ledger = audit_ledger
        self.event_bus = event_bus
        self.postcondition_verifier = postcondition_verifier

    def run(
        self,
        plan: AdminPlan,
        *,
        agent: str,
        mode: AutonomyMode,
        executor: PlanToolExecutor,
        approval_granted_steps: Sequence[str] = (),
        rollback_approval_granted_steps: Sequence[str] = (),
        trace_id: str | None = None,
    ) -> PlanExecutionResult:
        started = time.perf_counter()
        trace_id = trace_id or str(uuid.uuid4())
        steps_by_id = {step.step_id: step for step in plan.steps}
        order = plan.execution_order
        if not order or len(order) != len(steps_by_id) or set(order) != set(steps_by_id):
            return PlanExecutionResult("BLOCKED", trace_id, tuple(order), tuple(), None, tuple(), ("plan lacks a verified execution order",), _elapsed_ms(started))
        approved = set(approval_granted_steps)
        rollback_approved = set(rollback_approval_granted_steps)
        completed: list[str] = []
        execution_results: dict[str, Mapping[str, Any]] = {}
        rollback_completed: list[str] = []
        errors: list[str] = []
        for step_id in order:
            step_started = time.perf_counter()
            step = steps_by_id[step_id]
            decision = self.policy_gate.decide(step.tool, step.arguments, agent=agent, mode=mode, trace_id=trace_id, approval_granted=step_id in approved)
            if decision.status is not DecisionStatus.ALLOW:
                errors.append(f"{step_id}: {decision.status.value}: {decision.reason}")
                self._audit(trace_id, plan.task_id, "plan_step_blocked", decision.status.value, {"step_id": step_id, "reason": decision.reason, "duration_ms": _elapsed_ms(step_started)})
                return PlanExecutionResult("BLOCKED", trace_id, order, tuple(completed), step_id, tuple(rollback_completed), tuple(errors), _elapsed_ms(started))
            try:
                result = executor.execute(step)
                if not isinstance(result, Mapping):
                    raise PlanExecutionError(f"executor returned non-object result for {step_id}")
                execution_results[step_id] = dict(result)
                completed.append(step_id)
                if result.get("ok", True) is False:
                    raise PlanExecutionError(f"executor returned unsuccessful result for {step_id}")
                if self.postcondition_verifier is not None and step.expected:
                    postcondition = self.postcondition_verifier.verify(step.expected, result)
                    if not postcondition.valid:
                        self._audit(trace_id, plan.task_id, "plan_step_postcondition_failed", "FAILED", {"step_id": step_id, "errors": postcondition.errors, "result": sanitize(result), "duration_ms": _elapsed_ms(step_started)})
                        raise PlanExecutionError(f"postcondition failed for {step_id}: {'; '.join(postcondition.errors)}")
                self._audit(trace_id, plan.task_id, "plan_step_completed", "PASS", {"step_id": step_id, "result": sanitize(result), "duration_ms": _elapsed_ms(step_started)})
            except Exception as exc:
                error_detail = RiskAnalyzer.redact(str(exc))[:500]
                errors.append(f"{step_id}: {type(exc).__name__}: {error_detail}")
                self._audit(trace_id, plan.task_id, "plan_step_failed", "FAILED", {"step_id": step_id, "error": type(exc).__name__, "detail": error_detail, "duration_ms": _elapsed_ms(step_started)})
                for rollback_id in reversed(completed):
                    rollback_step = steps_by_id[rollback_id]
                    if not rollback_step.rollback_tool:
                        continue
                    rollback_decision = self.policy_gate.decide(rollback_step.rollback_tool, rollback_step.rollback_arguments, agent=agent, mode=mode, trace_id=trace_id, approval_granted=rollback_id in rollback_approved)
                    if rollback_decision.status is not DecisionStatus.ALLOW:
                        errors.append(f"{rollback_id}: rollback blocked: {rollback_decision.reason}")
                        continue
                    rollback_started = time.perf_counter()
                    try:
                        rollback_result = executor.rollback(rollback_step, execution_results[rollback_id])
                        if not isinstance(rollback_result, Mapping) or rollback_result.get("ok", True) is False:
                            raise PlanExecutionError(f"rollback returned unsuccessful result for {rollback_id}")
                        rollback_completed.append(rollback_id)
                        self._audit(trace_id, plan.task_id, "plan_step_rolled_back", "PASS", {"step_id": rollback_id, "result": sanitize(rollback_result), "duration_ms": _elapsed_ms(rollback_started)})
                    except Exception as rollback_exc:
                        rollback_detail = RiskAnalyzer.redact(str(rollback_exc))[:500]
                        errors.append(f"{rollback_id}: rollback {type(rollback_exc).__name__}: {rollback_detail}")
                rollback_candidates = [item for item in completed if steps_by_id[item].rollback_tool]
                if not rollback_candidates:
                    status: Literal["FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"] = "FAILED"
                elif len(rollback_completed) == len(rollback_candidates):
                    status = "ROLLED_BACK"
                else:
                    status = "ROLLBACK_FAILED"
                return PlanExecutionResult(status, trace_id, order, tuple(completed), step_id, tuple(rollback_completed), tuple(errors), _elapsed_ms(started))
        self._audit(trace_id, plan.task_id, "plan_completed", "COMPLETED", {"steps": completed, "duration_ms": _elapsed_ms(started)})
        return PlanExecutionResult("COMPLETED", trace_id, order, tuple(completed), None, tuple(), tuple(), _elapsed_ms(started))

    def _audit(self, trace_id: str, task_id: str, event_type: str, status: str, payload: Mapping[str, Any]) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(event_type, trace_id=trace_id, payload={"task_id": task_id, "status": status, **dict(payload)})
        if self.audit_ledger is None:
            return
        try:
            self.audit_ledger.append_event(trace_id=trace_id, task_id=task_id, event_type=event_type, actor="DAGPlanExecutor", status=status, payload=payload)
            duration_ms = payload.get("duration_ms")
            if isinstance(duration_ms, (int, float)) and hasattr(self.audit_ledger, "record_metric"):
                stage = "dag_execution" if event_type == "plan_completed" else "tool_execution"
                self.audit_ledger.record_metric(PerformanceMetric(trace_id, stage, status, float(duration_ms), {"event_type": event_type}))
        except Exception:
            return


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _normalize_iso_timestamp(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_embedding(embedding: Sequence[float]) -> tuple[float, ...]:
    try:
        values = tuple(_finite_float(item, name="embedding element") for item in embedding)
    except (TypeError, ValueError):
        raise ValueError("embedding must contain only finite real numeric elements") from None
    if not values or len(values) > MAX_EMBEDDING_DIM:
        raise ValueError("embedding must be a finite non-empty vector within the dimension limit")
    return values


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    a = _validate_embedding(left)
    b = _validate_embedding(right)
    if len(a) != len(b):
        raise ValueError("embedding dimensions do not match")
    numerator = sum(x * y for x, y in zip(a, b))
    denominator = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if denominator == 0 else numerator / denominator


class AuditLedger:
    """Hash-chained audit ledger and episodic vector memory in the AURA DB."""

    def __init__(self, db_path: str | Path = CANONICAL_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self._init_lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS aura_audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trace_id TEXT NOT NULL,
                        task_id TEXT,
                        event_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        idempotency_key TEXT UNIQUE,
                        created_at TEXT NOT NULL,
                        prev_hash TEXT,
                        transaction_hash TEXT,
                        hash_algorithm TEXT NOT NULL DEFAULT 'sha256'
                    );
                    CREATE INDEX IF NOT EXISTS idx_aura_audit_trace ON aura_audit_events(trace_id, id);
                    CREATE INDEX IF NOT EXISTS idx_aura_audit_task ON aura_audit_events(task_id, id);
                    CREATE TABLE IF NOT EXISTS aura_episodic_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        episode_type TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source_event_id INTEGER,
                        metadata_json TEXT NOT NULL,
                        memory_key TEXT UNIQUE,
                        created_at TEXT NOT NULL,
                        expires_at TEXT,
                        content_hash TEXT,
                        embedding_model TEXT,
                        embedding_dim INTEGER,
                        embedding_json TEXT,
                        FOREIGN KEY(source_event_id) REFERENCES aura_audit_events(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_aura_episode_task ON aura_episodic_memory(task_id, id);
                    CREATE INDEX IF NOT EXISTS idx_aura_episode_type ON aura_episodic_memory(episode_type, id);
                    CREATE INDEX IF NOT EXISTS idx_aura_episode_embedding ON aura_episodic_memory(embedding_model, embedding_dim, id);
                    CREATE TABLE IF NOT EXISTS aura_performance_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trace_id TEXT NOT NULL,
                        task_id TEXT,
                        stage TEXT NOT NULL,
                        status TEXT NOT NULL,
                        duration_ms REAL NOT NULL,
                        metadata_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_aura_perf_trace ON aura_performance_metrics(trace_id, id);
                    CREATE INDEX IF NOT EXISTS idx_aura_perf_stage ON aura_performance_metrics(stage, id);
                    CREATE TABLE IF NOT EXISTS aura_admin_schema_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO aura_admin_schema_meta(key, value, updated_at)
                    VALUES ('schema_version', '1', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                    CREATE TRIGGER IF NOT EXISTS trg_aura_audit_no_update
                    BEFORE UPDATE ON aura_audit_events
                    BEGIN SELECT RAISE(ABORT, 'aura audit events are append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS trg_aura_audit_no_delete
                    BEFORE DELETE ON aura_audit_events
                    BEGIN SELECT RAISE(ABORT, 'aura audit events are append-only'); END;
                    """
                )
                self._ensure_columns(connection, "aura_audit_events", {
                    "prev_hash": "TEXT",
                    "transaction_hash": "TEXT",
                    "hash_algorithm": "TEXT NOT NULL DEFAULT 'sha256'",
                })
                self._ensure_columns(connection, "aura_episodic_memory", {
                    "content_hash": "TEXT",
                    "embedding_model": "TEXT",
                    "embedding_dim": "INTEGER",
                    "embedding_json": "TEXT",
                })
            self._initialized = True

    @staticmethod
    def _ensure_columns(connection: sqlite3.Connection, table: str, columns: Mapping[str, str]) -> None:
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    @staticmethod
    def _hash_event(*, prev_hash: str, trace_id: str, task_id: str | None, event_type: str, actor: str, status: str, payload_json: str, idempotency_key: str | None, created_at: str) -> str:
        canonical = "|".join((prev_hash, trace_id, task_id or "", event_type, actor, status, payload_json, idempotency_key or "", created_at))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _last_hash(self, connection: sqlite3.Connection) -> str:
        row = connection.execute("SELECT transaction_hash FROM aura_audit_events WHERE transaction_hash IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        return str(row[0]) if row and row[0] else GENESIS_HASH

    def append_event(
        self,
        *,
        trace_id: str,
        task_id: str | None,
        event_type: str,
        actor: str,
        status: str,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        if not trace_id or not event_type or not actor or not status:
            raise ValueError("trace_id, event_type, actor and status are required")
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(sanitize(payload or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = connection.execute("SELECT id FROM aura_audit_events WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if existing:
                    return int(existing["id"])
            previous = self._last_hash(connection)
            transaction_hash = self._hash_event(prev_hash=previous, trace_id=trace_id, task_id=task_id, event_type=event_type, actor=actor, status=status, payload_json=payload_json, idempotency_key=idempotency_key, created_at=now)
            cursor = connection.execute(
                "INSERT INTO aura_audit_events(trace_id, task_id, event_type, actor, status, payload_json, idempotency_key, created_at, prev_hash, transaction_hash, hash_algorithm) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'sha256')",
                (trace_id, task_id, event_type, actor, status, payload_json, idempotency_key, now, previous, transaction_hash),
            )
            return int(cursor.lastrowid)

    def record_metric(self, metric: PerformanceMetric, *, task_id: str | None = None) -> int:
        if not metric.trace_id or not metric.stage or not metric.status:
            raise ValueError("trace_id, stage, status and non-negative duration_ms are required")
        try:
            duration_ms = _finite_float(metric.duration_ms, name="duration_ms", minimum=0.0)
        except ValueError:
            raise ValueError("trace_id, stage, status and non-negative duration_ms are required") from None
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(sanitize(metric.metadata), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO aura_performance_metrics(trace_id, task_id, stage, status, duration_ms, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (metric.trace_id, task_id, metric.stage, metric.status, duration_ms, metadata_json, now),
            )
            return int(cursor.lastrowid)

    def record_policy_decision(self, decision: PolicyDecision) -> int:
        return self.append_event(
            trace_id=decision.trace_id,
            task_id=None,
            event_type="policy_decision",
            actor="PolicyGate",
            status=decision.status.value,
            payload={"tool": decision.tool, "risk_level": decision.risk_level.value if decision.risk_level else None, "reason": decision.reason, "risk_score": decision.risk_report.score if decision.risk_report else None},
            idempotency_key=f"{decision.trace_id}:policy:{decision.tool}:{decision.status.value}",
        )

    def remember_episode(
        self,
        *,
        task_id: str,
        episode_type: str,
        summary: str,
        status: str,
        source_event_id: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        memory_key: str | None = None,
        expires_at: str | None = None,
        embedding: Sequence[float] | None = None,
        embedding_model: str | None = None,
    ) -> int:
        if not task_id or not episode_type or not summary or not status:
            raise ValueError("task_id, episode_type, summary and status are required")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
        normalized_status = status.strip().upper()
        if normalized_status not in _MEMORY_STATUSES:
            raise ValueError(f"unsupported memory status: {normalized_status}")
        if normalized_status == "FACT" and source_event_id is None:
            raise ValueError("FACT memory requires source_event_id provenance")
        vector = _validate_embedding(embedding) if embedding is not None else None
        if vector is not None and not embedding_model:
            raise ValueError("embedding_model is required when embedding is supplied")
        normalized_expires_at = _normalize_iso_timestamp(expires_at, field="expires_at") if expires_at is not None else None
        self.initialize()
        summary = summary[:MAX_TEXT]
        metadata_json = json.dumps(sanitize(metadata or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256((summary + "|" + metadata_json).encode("utf-8")).hexdigest()
        embedding_json = json.dumps(vector, separators=(",", ":")) if vector is not None else None
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if memory_key:
                existing = connection.execute("SELECT id FROM aura_episodic_memory WHERE memory_key = ?", (memory_key,)).fetchone()
                if existing:
                    return int(existing["id"])
            cursor = connection.execute(
                "INSERT INTO aura_episodic_memory(task_id, episode_type, summary, status, source_event_id, metadata_json, memory_key, created_at, expires_at, content_hash, embedding_model, embedding_dim, embedding_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, episode_type, summary, normalized_status, source_event_id, metadata_json, memory_key, now, normalized_expires_at, content_hash, embedding_model, len(vector) if vector else None, embedding_json),
            )
            return int(cursor.lastrowid)

    def trace_events(self, trace_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM aura_audit_events WHERE trace_id = ? ORDER BY id", (trace_id,)).fetchall()
        return [self._event_dict(row) for row in rows]

    def recent_episodes(self, *, task_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = _finite_int(limit, name="limit", minimum=1, maximum=500)
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            if task_id:
                rows = connection.execute("SELECT * FROM aura_episodic_memory WHERE (expires_at IS NULL OR expires_at > ?) AND task_id = ? ORDER BY id DESC LIMIT ?", (now, task_id, limit)).fetchall()
            else:
                rows = connection.execute("SELECT * FROM aura_episodic_memory WHERE (expires_at IS NULL OR expires_at > ?) ORDER BY id DESC LIMIT ?", (now, limit)).fetchall()
        return [self._episode_dict(row) for row in rows]

    def search_similar(self, query_embedding: Sequence[float], *, top_k: int = 5, embedding_model: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        query = _validate_embedding(query_embedding)
        top_k = _finite_int(top_k, name="top_k", minimum=1, maximum=100)
        self.initialize()
        clauses = ["embedding_json IS NOT NULL", "embedding_dim = ?", "(expires_at IS NULL OR expires_at > ?)"]
        params: list[Any] = [len(query), datetime.now(timezone.utc).isoformat()]
        if embedding_model:
            clauses.append("embedding_model = ?")
            params.append(embedding_model)
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM aura_episodic_memory WHERE {' AND '.join(clauses)} ORDER BY id DESC", tuple(params)).fetchall()
        matches: list[dict[str, Any]] = []
        for row in rows:
            try:
                vector = json.loads(row["embedding_json"])
                similarity = cosine_similarity(query, vector)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            item = self._episode_dict(row)
            item["similarity"] = round(similarity, 8)
            matches.append(item)
        matches.sort(key=lambda item: item["similarity"], reverse=True)
        return matches[:top_k]

    def verify_chain(self) -> dict[str, Any]:
        self.initialize()
        checked = 0
        legacy = 0
        errors: list[str] = []
        previous = GENESIS_HASH
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM aura_audit_events ORDER BY id").fetchall()
        for row in rows:
            checked += 1
            if not row["transaction_hash"] or not row["prev_hash"]:
                legacy += 1
                continue
            if row["prev_hash"] != previous:
                errors.append(f"id={row['id']}: prev_hash mismatch")
            expected = self._hash_event(prev_hash=row["prev_hash"], trace_id=row["trace_id"], task_id=row["task_id"], event_type=row["event_type"], actor=row["actor"], status=row["status"], payload_json=row["payload_json"], idempotency_key=row["idempotency_key"], created_at=row["created_at"])
            if expected != row["transaction_hash"]:
                errors.append(f"id={row['id']}: transaction_hash mismatch")
            previous = row["transaction_hash"]
        return {"valid": not errors and legacy == 0, "checked": checked, "legacy_unhashed": legacy, "errors": errors, "migration_required": legacy > 0, "algorithm": "sha256-chain"}

    def migration_plan(self) -> dict[str, Any]:
        integrity = self.verify_chain()
        if not integrity["migration_required"]:
            return {"status": "NOT_REQUIRED", "integrity": integrity, "steps": ()}
        return {
            "status": "MIGRATION_REQUIRED",
            "integrity": integrity,
            "steps": (
                "backup the canonical database read-only",
                "export legacy events with original row ids and payload hashes",
                "review the export independently",
                "create a new signed chain by explicit migration command",
                "retain the legacy database as immutable archive",
                "re-run verify_chain and health before enabling operational writes",
            ),
        }

    def retention_plan(self, *, as_of: str | None = None, limit: int = 500) -> dict[str, Any]:
        """Return a dry-run plan for expired episodes without mutating the ledger."""
        bounded_limit = _finite_int(limit, name="limit", minimum=1, maximum=5_000)
        self.initialize()
        as_of = _normalize_iso_timestamp(as_of or datetime.now(timezone.utc).isoformat(), field="as_of")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, task_id, episode_type, memory_key, created_at, expires_at FROM aura_episodic_memory WHERE expires_at IS NOT NULL AND expires_at <= ? ORDER BY id LIMIT ?",
                (as_of, bounded_limit + 1),
            ).fetchall()
        truncated = len(rows) > bounded_limit
        candidates = tuple({"id": int(row["id"]), "task_id": row["task_id"], "episode_type": row["episode_type"], "memory_key": row["memory_key"], "created_at": row["created_at"], "expires_at": row["expires_at"]} for row in rows[:bounded_limit])
        return {
            "status": "DRY_RUN",
            "as_of": as_of,
            "expired_count": len(candidates),
            "truncated": truncated,
            "candidates": candidates,
            "mutation_performed": False,
            "steps": (
                "review candidates and provenance",
                "archive approved records outside the canonical database",
                "delete only through an explicit audited retention command",
                "re-run health and memory search checks",
            ),
        }

    def health(self) -> dict[str, Any]:
        try:
            self.initialize()
            with self._connect() as connection:
                events = connection.execute("SELECT COUNT(*) AS count FROM aura_audit_events").fetchone()["count"]
                episodes = connection.execute("SELECT COUNT(*) AS count FROM aura_episodic_memory").fetchone()["count"]
                vectors = connection.execute("SELECT COUNT(*) AS count FROM aura_episodic_memory WHERE embedding_json IS NOT NULL").fetchone()["count"]
                metrics = connection.execute("SELECT COUNT(*) AS count FROM aura_performance_metrics").fetchone()["count"]
            chain = self.verify_chain()
            status = "READY" if chain["valid"] else "DEGRADED"
            return {"db_path": str(self.db_path), "audit_events": int(events), "episodic_memories": int(episodes), "vector_memories": int(vectors), "performance_metrics": int(metrics), "hash_chain": chain, "status": status}
        except (OSError, sqlite3.Error) as exc:
            return {"db_path": str(self.db_path), "status": "DEGRADED", "error_code": type(exc).__name__, "hash_chain": {"valid": False, "errors": ["ledger health unavailable"], "migration_required": False}}

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    @staticmethod
    def _episode_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        result.pop("embedding_json", None)
        return result


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> Sequence[float]: ...


class EpisodeDistiller(Protocol):
    def distill(self, text: str) -> str: ...


def compact_episode_text(text: str, *, max_chars: int = 4_000) -> str:
    """Deterministic fallback compaction used when no summarizer is available."""
    compacted = re.sub(r"\s+", " ", str(text)).strip()
    return compacted[:max_chars]


class EpisodicMemoryPipeline:
    """Distill short-term text, create an embedding and commit it to AuditLedger."""

    def __init__(self, ledger: AuditLedger, embedder: EmbeddingProvider, distiller: EpisodeDistiller | None = None, *, embedding_model: str = "configured") -> None:
        if not embedding_model.strip():
            raise ValueError("embedding_model cannot be empty")
        self.ledger = ledger
        self.embedder = embedder
        self.distiller = distiller
        self.embedding_model = embedding_model.strip()

    def commit(
        self,
        *,
        task_id: str,
        episode_type: str,
        raw_text: str,
        status: str,
        metadata: Mapping[str, Any] | None = None,
        memory_key: str | None = None,
        source_event_id: int | None = None,
        expires_at: str | None = None,
    ) -> int:
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("raw_text must be a non-empty string")
        if len(raw_text) > MAX_TEXT:
            raise ValueError("raw_text exceeds maximum size")
        summary = self.distiller.distill(raw_text) if self.distiller is not None else compact_episode_text(raw_text)
        summary = compact_episode_text(summary)
        if not summary:
            raise ValueError("episode summary cannot be empty")
        vector = _validate_embedding(self.embedder.embed(summary))
        return self.ledger.remember_episode(
            task_id=task_id,
            episode_type=episode_type,
            summary=summary,
            status=status,
            source_event_id=source_event_id,
            metadata=metadata,
            memory_key=memory_key,
            expires_at=expires_at,
            embedding=vector,
            embedding_model=self.embedding_model,
        )


class AdminKernel:
    """Safe integration point: plan, verify and audit; never execute tools."""

    def __init__(self, planner: GLMPlanner, ledger: AuditLedger, *, actor: str = "aura-admin") -> None:
        self.planner = planner
        self.ledger = ledger
        self.actor = actor
        self._safe_initialize()

    def _safe_initialize(self) -> None:
        try:
            self.ledger.initialize()
        except Exception:
            return

    def _safe_append(self, **kwargs: Any) -> None:
        try:
            self.ledger.append_event(**kwargs)
        except Exception:
            return

    def _safe_episode(self, **kwargs: Any) -> None:
        try:
            self.ledger.remember_episode(**kwargs)
        except Exception:
            return

    def assess(self, *, task_id: str, goal: str, context: Mapping[str, Any], agent: str, mode: AutonomyMode) -> PlannerResult:
        trace_id = str(uuid.uuid4())
        self._safe_append(trace_id=trace_id, task_id=task_id, event_type="plan_requested", actor=self.actor, status="RECEIVED", payload={"goal": goal, "mode": mode.value, "agent": agent}, idempotency_key=f"{trace_id}:plan_requested")
        result = self.planner.plan(task_id=task_id, goal=goal, context=context, agent=agent, mode=mode, trace_id=trace_id)
        self._safe_append(trace_id=trace_id, task_id=task_id, event_type="plan_verified", actor=self.actor, status=result.status, payload={"errors": result.verification.errors, "warnings": result.verification.warnings, "required_approvals": result.verification.required_approvals}, idempotency_key=f"{trace_id}:plan_verified")
        if result.verification.valid and result.verification.plan:
            self._safe_episode(task_id=task_id, episode_type="plan", summary=result.verification.plan.goal, status="PLANNED", metadata={"trace_id": trace_id, "step_count": len(result.verification.plan.steps), "mode": mode.value}, memory_key=f"{trace_id}:plan")
        return result


__all__ = [
    "AdminKernel", "AdminPlan", "ApprovalValidator", "AuditLedger", "AutonomyMode", "CANONICAL_DB_PATH",
    "DAGPlanExecutor", "DecisionStatus", "EmbeddingProvider", "EpisodeDistiller", "EpisodicMemoryPipeline",
    "EventBus", "GLMPlanner", "GENESIS_HASH", "MAX_PLAN_STEPS", "PerformanceMetric", "PlanExecutionError",
    "PlanExecutionResult", "PlanInvariantChecker", "PlanStep", "PlanToolExecutor", "PlanVerification", "PlanVerifier",
    "PlannerResult", "PolicyDecision", "PolicyGate", "PolicyInterceptor", "PolicyViolation", "RiskAnalyzer",
    "RiskFinding", "RiskLevel", "RiskReport", "StructuredModelAdapter", "ToolManifest", "ToolRegistry",
    "ToolRiskValidator", "cosine_similarity", "compact_episode_text", "load_structured_document", "sanitize",
]


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=CANONICAL_DB_PATH)
    parser.add_argument("--init-db", action="store_true", help="initialize the canonical audit and episodic-memory tables")
    parser.add_argument("--verify-chain", action="store_true", help="verify the SHA-256 audit chain")
    parser.add_argument("--migration-plan", action="store_true", help="show a read-only legacy-chain migration plan")
    parser.add_argument("--retention-plan", action="store_true", help="show a read-only expired-memory retention plan")
    args = parser.parse_args()
    ledger = AuditLedger(args.db)
    if args.init_db:
        ledger.initialize()
    if args.verify_chain:
        print(json.dumps(ledger.verify_chain(), ensure_ascii=False, indent=2))
    elif args.migration_plan:
        print(json.dumps(ledger.migration_plan(), ensure_ascii=False, indent=2))
    elif args.retention_plan:
        print(json.dumps(ledger.retention_plan(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(ledger.health(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
