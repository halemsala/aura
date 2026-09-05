#!/usr/bin/env python3
"""Governance helpers for the AURA administrator control plane.

The helpers are framework-neutral and dependency-free. They do not execute
commands or grant authority to a model; they make human approvals, context
boundaries, failure recovery and postconditions explicit and testable.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import threading
import time
from contextlib import contextmanager
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

try:
    from .aura_admin_core import RiskAnalyzer, sanitize
except ImportError:
    from aura_admin_core import RiskAnalyzer, sanitize


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class ApprovalGrant:
    grant_id: str
    task_id: str
    trace_id: str
    tool: str
    arguments_digest: str
    mode: str
    approver: str
    issued_at: float
    expires_at: float
    signature: str


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


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _bounded_int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


class ApprovalBroker:
    """Issue and validate short-lived approvals bound to one exact action."""

    def __init__(self, signing_secret: bytes, *, default_ttl_s: float = 300.0) -> None:
        if not isinstance(signing_secret, bytes) or len(signing_secret) < 32:
            raise ValueError("signing_secret must contain at least 32 bytes")
        _finite_float(default_ttl_s, name="default_ttl_s", minimum=0.0, maximum=3_600.0)
        if default_ttl_s == 0:
            raise ValueError("default_ttl_s must be between 0 and 3600 seconds")
        self._secret = bytes(signing_secret)
        self.default_ttl_s = float(default_ttl_s)
        self._used_grants: set[str] = set()
        self._lock = threading.RLock()

    @staticmethod
    def arguments_digest(arguments: Mapping[str, Any]) -> str:
        if not isinstance(arguments, Mapping):
            raise ValueError("approval arguments must be an object")
        try:
            payload = json.dumps(dict(arguments), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("approval arguments are not safely serializable") from exc
        if len(payload) > 64_000:
            raise ValueError("approval arguments exceed maximum serialized size")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _signature(self, *, grant_id: str, task_id: str, trace_id: str, tool: str, arguments_digest: str, mode: str, approver: str, issued_at: float, expires_at: float) -> str:
        payload = "|".join((grant_id, task_id, trace_id, tool, arguments_digest, mode, approver, f"{issued_at:.6f}", f"{expires_at:.6f}"))
        return hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def issue(self, *, task_id: str, trace_id: str, tool: str, arguments: Mapping[str, Any], mode: str, approver: str, ttl_s: float | None = None, now: float | None = None) -> ApprovalGrant:
        if not all(isinstance(value, str) and value.strip() for value in (task_id, trace_id, tool, mode, approver)):
            raise ValueError("task_id, trace_id, tool, mode and approver are required")
        ttl = self.default_ttl_s if ttl_s is None else _finite_float(ttl_s, name="ttl_s", minimum=0.0, maximum=3_600.0)
        if ttl <= 0:
            raise ValueError("ttl_s must be between 0 and 3600 seconds")
        issued_at = time.time() if now is None else _finite_float(now, name="now")
        expires_at = issued_at + ttl
        grant_id = str(uuid.uuid4())
        digest = self.arguments_digest(arguments)
        signature = self._signature(grant_id=grant_id, task_id=task_id, trace_id=trace_id, tool=tool, arguments_digest=digest, mode=mode, approver=approver, issued_at=issued_at, expires_at=expires_at)
        return ApprovalGrant(grant_id, task_id, trace_id, tool, digest, mode, approver, issued_at, expires_at, signature)

    def _validate_unlocked(self, grant: ApprovalGrant, *, task_id: str, trace_id: str, tool: str, arguments: Mapping[str, Any], mode: str, now: float, consume: bool) -> bool:
        if not isinstance(grant, ApprovalGrant):
            return False
        if consume and grant.grant_id in self._used_grants:
            return False
        if not all(isinstance(value, str) and value.strip() for value in (grant.grant_id, grant.task_id, grant.trace_id, grant.tool, grant.arguments_digest, grant.mode, grant.approver, grant.signature)):
            return False
        if not all(_is_finite_number(value) for value in (grant.issued_at, grant.expires_at, now)):
            return False
        if now >= grant.expires_at or grant.expires_at <= grant.issued_at:
            return False
        if (grant.task_id, grant.trace_id, grant.tool, grant.mode) != (task_id, trace_id, tool, mode):
            return False
        try:
            arguments_digest = self.arguments_digest(arguments)
        except (TypeError, ValueError, RecursionError):
            return False
        if grant.arguments_digest != arguments_digest:
            return False
        expected = self._signature(grant_id=grant.grant_id, task_id=grant.task_id, trace_id=grant.trace_id, tool=grant.tool, arguments_digest=grant.arguments_digest, mode=grant.mode, approver=grant.approver, issued_at=float(grant.issued_at), expires_at=float(grant.expires_at))
        valid = hmac.compare_digest(expected, grant.signature)
        if valid and consume:
            self._used_grants.add(grant.grant_id)
        return valid

    def validate(self, grant: ApprovalGrant, *, task_id: str, trace_id: str, tool: str, arguments: Mapping[str, Any], mode: str, now: float | None = None, consume: bool = False) -> bool:
        with self._lock:
            try:
                current = time.time() if now is None else _finite_float(now, name="now")
            except ValueError:
                return False
            return self._validate_unlocked(grant, task_id=task_id, trace_id=trace_id, tool=tool, arguments=arguments, mode=mode, now=current, consume=consume)

    def consume_many(self, requests: Sequence[tuple[ApprovalGrant, str, str, str, Mapping[str, Any], str]], *, now: float | None = None) -> bool:
        """Validate and consume a complete approval set atomically."""
        with self._lock:
            try:
                current = time.time() if now is None else _finite_float(now, name="now")
                if not isinstance(requests, Sequence) or isinstance(requests, (str, bytes, bytearray)) or not requests:
                    return False
                normalized: list[tuple[ApprovalGrant, str, str, str, Mapping[str, Any], str]] = []
                for request in requests:
                    if not isinstance(request, (tuple, list)) or len(request) != 6:
                        return False
                    normalized.append(tuple(request))  # type: ignore[arg-type]
            except (TypeError, ValueError, RecursionError):
                return False
            grants = [request[0] for request in normalized]
            if len({grant.grant_id for grant in grants if isinstance(grant, ApprovalGrant)}) != len(normalized):
                return False
            if not all(self._validate_unlocked(grant, task_id=task_id, trace_id=trace_id, tool=tool, arguments=arguments, mode=mode, now=current, consume=False) for grant, task_id, trace_id, tool, arguments, mode in normalized):
                return False
            self._used_grants.update(grant.grant_id for grant in grants)
            return True


@dataclass(frozen=True)
class ContextResult:
    safe: bool
    context: dict[str, Any]
    report: Any
    errors: tuple[str, ...] = ()


class ContextBuilder:
    """Build bounded, sanitized context without importing instructions as policy."""

    MAX_CHARS = 128_000

    def __init__(self, *, allowed_keys: Sequence[str] | None = None, max_chars: int = 32_000, risk_analyzer: RiskAnalyzer | None = None) -> None:
        if allowed_keys is None:
            normalized_keys: tuple[str, ...] = ()
        elif isinstance(allowed_keys, str) or not isinstance(allowed_keys, Sequence):
            raise ValueError("allowed_keys must be a sequence of non-empty strings")
        else:
            normalized: list[str] = []
            for item in allowed_keys:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("allowed_keys must be a sequence of non-empty strings")
                normalized.append(item.strip())
            normalized_keys = tuple(normalized)
        self.allowed_keys = frozenset(normalized_keys)
        self.max_chars = _bounded_int(max_chars, name="max_chars", minimum=1_000, maximum=self.MAX_CHARS)
        self.risk_analyzer = risk_analyzer or RiskAnalyzer()

    def build(self, raw_context: Mapping[str, Any], *, trace_id: str | None = None, scope_terms: Sequence[str] | None = None) -> ContextResult:
        if not isinstance(raw_context, Mapping):
            report = self.risk_analyzer.analyze(str(raw_context), direction="prompt", trace_id=trace_id)
            return ContextResult(False, {}, report, ("context must be an object",))
        sanitized = sanitize(raw_context)
        raw_serialized = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(raw_serialized) > self.max_chars:
            report = self.risk_analyzer.analyze(raw_serialized[: self.max_chars], direction="prompt", trace_id=trace_id, allowed_scope=scope_terms)
            return ContextResult(False, {}, report, ("context exceeds max_chars",))
        raw_report = self.risk_analyzer.analyze(raw_serialized, direction="prompt", trace_id=trace_id, allowed_scope=scope_terms)
        if not raw_report.is_safe:
            return ContextResult(False, {}, raw_report, ("context blocked by risk policy",))
        if self.allowed_keys:
            sanitized = {key: value for key, value in sanitized.items() if key in self.allowed_keys}
        serialized = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        report = self.risk_analyzer.analyze(serialized, direction="prompt", trace_id=trace_id, allowed_scope=scope_terms)
        if not report.is_safe:
            return ContextResult(False, {}, report, ("context blocked by risk policy",))
        return ContextResult(True, sanitized, report)


class CircuitBreaker:
    """Thread-safe bounded failure breaker for GLM, DB or external adapters."""

    def __init__(self, *, failure_threshold: int = 3, cooldown_s: float = 30.0, clock: Callable[[], float] | None = None) -> None:
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int) or not 1 <= failure_threshold <= 1_000:
            raise ValueError("failure_threshold must be an integer between 1 and 1000")
        self.failure_threshold = failure_threshold
        self.cooldown_s = _finite_float(cooldown_s, name="cooldown_s", minimum=0.0, maximum=3_600.0)
        if self.cooldown_s <= 0:
            raise ValueError("cooldown_s must be positive")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable")
        self._clock = clock or time.time
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = threading.RLock()

    @property
    def state(self) -> BreakerState:
        with self._lock:
            self._refresh(self._clock_now())
            return self._state

    def _clock_now(self, now: float | None = None) -> float:
        return _finite_float(self._clock() if now is None else now, name="now")

    def _refresh(self, now: float | None = None) -> None:
        current = self._clock_now(now)
        if self._state is BreakerState.OPEN and self._opened_at is not None and current - self._opened_at >= self.cooldown_s:
            self._state = BreakerState.HALF_OPEN

    def allow(self, *, now: float | None = None) -> bool:
        with self._lock:
            try:
                current = self._clock_now(now)
            except ValueError:
                return False
            self._refresh(current)
            if self._state is BreakerState.OPEN:
                return False
            if self._state is BreakerState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    return False
                self._half_open_probe_in_flight = True
                return True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = BreakerState.CLOSED
            self._failures = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

    def record_failure(self, *, now: float | None = None) -> None:
        with self._lock:
            current = self._clock_now(now)
            self._refresh(current)
            if self._state is BreakerState.HALF_OPEN:
                self._state = BreakerState.OPEN
                self._opened_at = current
                self._half_open_probe_in_flight = False
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = BreakerState.OPEN
                self._opened_at = current

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh(self._clock_now())
            return {"state": self._state.value, "failures": self._failures, "opened_at": self._opened_at, "cooldown_s": self.cooldown_s, "half_open_probe_in_flight": self._half_open_probe_in_flight}


class KeyedLockManager:
    """Serialize work per AURA resource without imposing a global lock."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.RLock()

    @contextmanager
    def hold(self, resource: str, *, timeout_s: float = 0.0):
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError("resource must be a non-empty string")
        timeout = _finite_float(timeout_s, name="timeout_s", minimum=0.0, maximum=30.0)
        with self._guard:
            lock = self._locks.setdefault(resource, threading.Lock())
        acquired = lock.acquire(timeout=timeout) if timeout else lock.acquire(blocking=False)
        if not acquired:
            raise TimeoutError(f"resource lock unavailable: {resource}")
        try:
            yield
        finally:
            lock.release()


@dataclass(frozen=True)
class RetryResult:
    value: Any
    attempts: int


@dataclass(frozen=True)
class RetryPolicy:
    """Retry only explicitly idempotent operations and bounded exceptions."""

    max_attempts: int = 1
    backoff_s: float = 0.0
    max_backoff_s: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (TimeoutError, ConnectionError)

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int) or not 1 <= self.max_attempts <= 5:
            raise ValueError("max_attempts must be an integer between 1 and 5")
        backoff = _finite_float(self.backoff_s, name="backoff_s", minimum=0.0, maximum=30.0)
        max_backoff = _finite_float(self.max_backoff_s, name="max_backoff_s", minimum=0.0, maximum=30.0)
        if backoff > max_backoff:
            raise ValueError("backoff bounds are invalid")
        object.__setattr__(self, "backoff_s", backoff)
        object.__setattr__(self, "max_backoff_s", max_backoff)

    def run(self, operation: Callable[[], Any], *, idempotent: bool, sleep: Callable[[float], None] = time.sleep) -> RetryResult:
        if self.max_attempts > 1 and not idempotent:
            raise ValueError("retries require an idempotent operation")
        attempts = 0
        while attempts < self.max_attempts:
            attempts += 1
            try:
                return RetryResult(operation(), attempts)
            except self.retryable_exceptions:
                if attempts >= self.max_attempts:
                    raise
                sleep(min(self.max_backoff_s, self.backoff_s * (2 ** (attempts - 1))))
        raise RuntimeError("retry loop exhausted unexpectedly")


@dataclass(frozen=True)
class BudgetResult:
    stage: str
    duration_ms: float
    budget_ms: float
    within_budget: bool
    overage_ms: float


class PerformanceBudget:
    """Evaluate measured stage latency against explicit, non-authoritative budgets."""

    def __init__(self, budgets_ms: Mapping[str, float], *, default_ms: float | None = None) -> None:
        if not isinstance(budgets_ms, Mapping):
            raise ValueError("budgets_ms must be a mapping")
        if not budgets_ms and default_ms is None:
            raise ValueError("at least one budget or a default budget is required")
        normalized: dict[str, float] = {}
        for stage, limit in budgets_ms.items():
            if not isinstance(stage, str) or not stage.strip():
                raise ValueError("stage names must be non-empty strings")
            try:
                numeric_limit = _finite_float(limit, name="budget")
            except ValueError:
                raise ValueError("budgets must be finite positive numbers") from None
            if numeric_limit <= 0:
                raise ValueError("budgets must be finite positive numbers")
            normalized[stage.strip()] = numeric_limit
        if default_ms is not None:
            try:
                numeric_default = _finite_float(default_ms, name="default_ms")
            except ValueError:
                raise ValueError("default_ms must be a finite positive number") from None
            if numeric_default <= 0:
                raise ValueError("default_ms must be a finite positive number")
        else:
            numeric_default = None
        self._budgets = normalized
        self._default_ms = numeric_default

    def evaluate(self, stage: str, duration_ms: float) -> BudgetResult:
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError("stage must be a non-empty string")
        stage = stage.strip()
        if stage not in self._budgets and self._default_ms is None:
            raise KeyError(f"no performance budget for stage: {stage}")
        try:
            numeric_duration = _finite_float(duration_ms, name="duration_ms", minimum=0.0)
        except ValueError:
            raise ValueError("duration_ms must be a finite non-negative number") from None
        budget = self._budgets.get(stage, self._default_ms)
        assert budget is not None
        overage = max(0.0, numeric_duration - budget)
        return BudgetResult(stage, numeric_duration, budget, overage == 0.0, overage)


@dataclass(frozen=True)
class PostconditionResult:
    valid: bool
    errors: tuple[str, ...]


class PostconditionVerifier:
    """Compare expected output constraints with an executor result."""

    def verify(self, expected: Mapping[str, Any], actual: Mapping[str, Any]) -> PostconditionResult:
        errors: list[str] = []
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return PostconditionResult(False, ("expected and actual must be objects",))
        self._compare(expected, actual, "$", errors)
        return PostconditionResult(not errors, tuple(errors))

    def _compare(self, expected: Any, actual: Any, path: str, errors: list[str]) -> None:
        if isinstance(expected, Mapping):
            if not isinstance(actual, Mapping):
                errors.append(f"{path}: expected object")
                return
            for key, value in expected.items():
                if key not in actual:
                    errors.append(f"{path}.{key}: missing")
                else:
                    self._compare(value, actual[key], f"{path}.{key}", errors)
        elif isinstance(expected, list):
            if not isinstance(actual, list) or not all(item in actual for item in expected):
                errors.append(f"{path}: expected list values not present")
        elif expected != actual:
            errors.append(f"{path}: expected {expected!r}, got {actual!r}")


__all__ = ["ApprovalBroker", "ApprovalGrant", "BreakerState", "BudgetResult", "CircuitBreaker", "ContextBuilder", "ContextResult", "KeyedLockManager", "PerformanceBudget", "PostconditionResult", "PostconditionVerifier", "RetryPolicy", "RetryResult"]
