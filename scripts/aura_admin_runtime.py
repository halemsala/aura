#!/usr/bin/env python3
"""Safe orchestration facade for the AURA administrator control plane."""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Literal, Mapping

try:
    from .aura_admin_core import (
        AdminPlan,
        AuditLedger,
        AutonomyMode,
        DAGPlanExecutor,
        DecisionStatus,
        PlanExecutionResult,
        PlanToolExecutor,
        PlannerResult,
    )
    from .aura_admin_governance import ApprovalBroker, ApprovalGrant, CircuitBreaker, ContextBuilder, KeyedLockManager, PostconditionVerifier, _finite_float
except ImportError:
    from aura_admin_core import (
        AdminPlan,
        AuditLedger,
        AutonomyMode,
        DAGPlanExecutor,
        DecisionStatus,
        PlanExecutionResult,
        PlanToolExecutor,
        PlannerResult,
    )
    from aura_admin_governance import ApprovalBroker, ApprovalGrant, CircuitBreaker, ContextBuilder, KeyedLockManager, PostconditionVerifier, _finite_float


@dataclass(frozen=True)
class RuntimeResult:
    status: Literal["BLOCKED_CONTEXT", "GLM_UNAVAILABLE", "PLAN_INVALID", "PLAN_READY", "APPROVAL_REQUIRED", "AUDIT_UNAVAILABLE", "BLOCKED", "COMPLETED", "FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"]
    trace_id: str
    planner: PlannerResult | None
    execution: PlanExecutionResult | None
    errors: tuple[str, ...] = ()


class AdminRuntime:
    """Compose administrator stages without allowing the planner to execute tools."""

    def __init__(
        self,
        planner: Any,
        ledger: AuditLedger,
        tool_executor: PlanToolExecutor,
        *,
        agent: str = "aura-admin",
        context_builder: ContextBuilder | None = None,
        approval_broker: ApprovalBroker | None = None,
        glm_breaker: CircuitBreaker | None = None,
        plan_executor: DAGPlanExecutor | None = None,
        require_ledger_for_side_effects: bool = True,
        lock_manager: KeyedLockManager | None = None,
        lock_timeout_s: float = 0.0,
    ) -> None:
        self.planner = planner
        self.ledger = ledger
        self.tool_executor = tool_executor
        self.agent = agent
        self.context_builder = context_builder or ContextBuilder()
        self.approval_broker = approval_broker
        self.glm_breaker = glm_breaker or CircuitBreaker()
        if not isinstance(require_ledger_for_side_effects, bool):
            raise ValueError("require_ledger_for_side_effects must be a boolean")
        self.require_ledger_for_side_effects = require_ledger_for_side_effects
        self.lock_manager = lock_manager
        self.lock_timeout_s = _finite_float(lock_timeout_s, name="lock_timeout_s", minimum=0.0, maximum=30.0)
        self.plan_executor = plan_executor or DAGPlanExecutor(planner.verifier.policy_gate, ledger, postcondition_verifier=PostconditionVerifier())

    def run(
        self,
        *,
        task_id: str,
        goal: str,
        raw_context: Mapping[str, Any],
        mode: AutonomyMode = AutonomyMode.PLAN_ONLY,
        execute: bool = False,
        approvals: Mapping[str, ApprovalGrant] | None = None,
        rollback_approvals: Mapping[str, ApprovalGrant] | None = None,
        trace_id: str | None = None,
    ) -> RuntimeResult:
        trace_id = trace_id or str(uuid.uuid4())
        if approvals is not None and not isinstance(approvals, Mapping):
            error = ("approvals must be an object keyed by step_id",)
            self._audit(trace_id, task_id, "execution_blocked", "REQUIRE_APPROVAL", {"errors": error})
            return RuntimeResult("APPROVAL_REQUIRED", trace_id, None, None, error)
        if rollback_approvals is not None and not isinstance(rollback_approvals, Mapping):
            error = ("rollback_approvals must be an object keyed by step_id",)
            self._audit(trace_id, task_id, "execution_blocked", "REQUIRE_APPROVAL", {"errors": error})
            return RuntimeResult("APPROVAL_REQUIRED", trace_id, None, None, error)
        try:
            context = self.context_builder.build(raw_context, trace_id=trace_id)
        except Exception as exc:
            error = (f"context builder failed: {type(exc).__name__}",)
            self._audit(trace_id, task_id, "context_failed", "FAILED", {"errors": error})
            return RuntimeResult("BLOCKED_CONTEXT", trace_id, None, None, error)
        if not context.safe:
            self._audit(trace_id, task_id, "context_blocked", "BLOCKED", {"errors": context.errors, "risk_score": context.report.score})
            return RuntimeResult("BLOCKED_CONTEXT", trace_id, None, None, context.errors)
        if not self.glm_breaker.allow():
            error = ("GLM circuit breaker is open",)
            self._audit(trace_id, task_id, "planner_blocked", "BLOCKED", {"errors": error})
            return RuntimeResult("GLM_UNAVAILABLE", trace_id, None, None, error)
        try:
            planner_result = self.planner.plan(task_id=task_id, goal=goal, context=context.context, agent=self.agent, mode=mode, trace_id=trace_id)
        except Exception as exc:
            self.glm_breaker.record_failure()
            error = (f"planner failed: {type(exc).__name__}",)
            self._audit(trace_id, task_id, "planner_failed", "FAILED", {"errors": error})
            return RuntimeResult("PLAN_INVALID", trace_id, None, None, error)
        if planner_result.status != "VALID" or planner_result.verification.plan is None:
            self.glm_breaker.record_failure()
            self._audit(trace_id, task_id, "plan_rejected", "INVALID", {"errors": planner_result.verification.errors, "latency_ms": planner_result.latency_ms})
            return RuntimeResult("PLAN_INVALID", trace_id, planner_result, None, planner_result.verification.errors)
        self.glm_breaker.record_success()
        plan = planner_result.verification.plan
        required = set(planner_result.verification.required_approvals)
        execution_mode = execute and mode not in {AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DRY_RUN, AutonomyMode.DISABLED}
        primary_approvals = approvals or {}
        rollback_approval_map = rollback_approvals or {}
        approved = self._approved_steps(plan, trace_id, mode, primary_approvals)
        rollback_approved = self._approved_rollback_steps(plan, trace_id, mode, rollback_approval_map)
        if execution_mode:
            primary_required, rollback_required = self._approval_requirements(plan, trace_id, mode, required)
        else:
            primary_required, rollback_required = required, set()
        if execution_mode and self.require_ledger_for_side_effects and any(self._is_side_effecting(step) for step in plan.steps) and not self._ledger_ready():
            error = ("canonical audit ledger unavailable for side-effecting execution",)
            self._audit(trace_id, task_id, "execution_blocked", "AUDIT_UNAVAILABLE", {"plan_hash": plan.fingerprint(), "errors": error})
            return RuntimeResult("AUDIT_UNAVAILABLE", trace_id, planner_result, None, error)
        missing = tuple(sorted(primary_required - approved))
        if not execute or mode in {AutonomyMode.OBSERVE, AutonomyMode.PLAN_ONLY, AutonomyMode.DRY_RUN, AutonomyMode.DISABLED}:
            status = "APPROVAL_REQUIRED" if missing else "PLAN_READY"
            self._audit(trace_id, task_id, "plan_ready", status, {"plan_hash": plan.fingerprint(), "required_approvals": sorted(required), "approved": sorted(approved)})
            return RuntimeResult(status, trace_id, planner_result, None, tuple(f"approval required for {step_id}" for step_id in missing))
        if missing:
            self._audit(trace_id, task_id, "execution_blocked", "REQUIRE_APPROVAL", {"plan_hash": plan.fingerprint(), "missing": missing})
            return RuntimeResult("APPROVAL_REQUIRED", trace_id, planner_result, None, tuple(f"approval required for {step_id}" for step_id in missing))
        try:
            with ExitStack() as lock_stack:
                if self.lock_manager is not None:
                    for resource in self._plan_resources(plan):
                        lock_stack.enter_context(self.lock_manager.hold(resource, timeout_s=self.lock_timeout_s))
                if self.approval_broker is not None and (primary_required or rollback_required):
                    consumed_primary, consumed_rollback, consumed = self._consume_required_approvals(plan, trace_id, mode, primary_approvals, rollback_approval_map, primary_required, rollback_required)
                    if not consumed:
                        error = ("approval bundle invalid or incomplete",)
                        self._audit(trace_id, task_id, "execution_blocked", "REQUIRE_APPROVAL", {"plan_hash": plan.fingerprint(), "errors": error})
                        return RuntimeResult("APPROVAL_REQUIRED", trace_id, planner_result, None, error)
                    approved.update(consumed_primary)
                    rollback_approved.update(consumed_rollback)
                execution = self.plan_executor.run(plan, agent=self.agent, mode=mode, executor=self.tool_executor, approval_granted_steps=tuple(sorted(approved)), rollback_approval_granted_steps=tuple(sorted(rollback_approved)), trace_id=trace_id)
        except TimeoutError as exc:
            error = (f"resource lock unavailable: {str(exc)}",)
            self._audit(trace_id, task_id, "execution_blocked", "LOCK_UNAVAILABLE", {"errors": error, "plan_hash": plan.fingerprint()})
            return RuntimeResult("BLOCKED", trace_id, planner_result, None, error)
        return RuntimeResult(execution.status, trace_id, planner_result, execution, execution.errors)

    def _plan_resources(self, plan: AdminPlan) -> tuple[str, ...]:
        resources: set[str] = set()
        for step in plan.steps:
            if not self._is_side_effecting(step):
                continue
            arguments = step.arguments if isinstance(step.arguments, Mapping) else {}
            service = arguments.get("service")
            if isinstance(service, str) and service.strip():
                resources.add(f"service:{service.strip()}")
            try:
                manifest = self.planner.verifier.policy_gate.registry.get(step.tool)
            except Exception:
                manifest = None
            if manifest is not None:
                resources.update(f"effect:{effect}" for effect in manifest.side_effects if isinstance(effect, str) and effect.strip())
        return tuple(sorted(resources))

    def _is_side_effecting(self, step: Any) -> bool:
        try:
            manifest = self.planner.verifier.policy_gate.registry.get(step.tool)
        except Exception:
            return True
        return bool(manifest is None or manifest.side_effects)

    def _ledger_ready(self) -> bool:
        try:
            health = self.ledger.health()
        except Exception:
            return False
        return isinstance(health, Mapping) and health.get("status") == "READY"

    def _approved_steps(self, plan: AdminPlan, trace_id: str, mode: AutonomyMode, approvals: Mapping[str, ApprovalGrant]) -> set[str]:
        if self.approval_broker is None:
            return set()
        approved: set[str] = set()
        for step in plan.steps:
            try:
                grant = approvals.get(step.step_id)
                valid = grant is not None and self.approval_broker.validate(grant, task_id=plan.task_id, trace_id=trace_id, tool=step.tool, arguments=step.arguments, mode=mode.value)
            except Exception:
                valid = False
            if valid:
                approved.add(step.step_id)
        return approved

    def _approved_rollback_steps(self, plan: AdminPlan, trace_id: str, mode: AutonomyMode, approvals: Mapping[str, ApprovalGrant]) -> set[str]:
        if self.approval_broker is None:
            return set()
        approved: set[str] = set()
        for step in plan.steps:
            if not step.rollback_tool:
                continue
            try:
                grant = approvals.get(step.step_id)
                valid = grant is not None and self.approval_broker.validate(grant, task_id=plan.task_id, trace_id=trace_id, tool=step.rollback_tool, arguments=step.rollback_arguments, mode=mode.value)
            except Exception:
                valid = False
            if valid:
                approved.add(step.step_id)
        return approved

    def _approval_requirements(self, plan: AdminPlan, trace_id: str, mode: AutonomyMode, planned_required: set[str]) -> tuple[set[str], set[str]]:
        primary_required: set[str] = set()
        rollback_required: set[str] = set()
        policy_gate = self.plan_executor.policy_gate
        for step in plan.steps:
            try:
                primary_decision = policy_gate.decide(step.tool, step.arguments, agent=self.agent, mode=mode, trace_id=trace_id, approval_granted=False)
                if primary_decision.status is DecisionStatus.REQUIRE_APPROVAL:
                    primary_required.add(step.step_id)
                if step.rollback_tool:
                    rollback_decision = policy_gate.decide(step.rollback_tool, step.rollback_arguments, agent=self.agent, mode=mode, trace_id=trace_id, approval_granted=False)
                    if rollback_decision.status is DecisionStatus.REQUIRE_APPROVAL:
                        rollback_required.add(step.step_id)
            except Exception:
                primary_required.add(step.step_id)
        required = primary_required | rollback_required
        if not required.issubset(planned_required):
            primary_required.update(planned_required - required)
        return primary_required, rollback_required

    def _consume_required_approvals(
        self,
        plan: AdminPlan,
        trace_id: str,
        mode: AutonomyMode,
        approvals: Mapping[str, ApprovalGrant],
        rollback_approvals: Mapping[str, ApprovalGrant],
        primary_required: set[str],
        rollback_required: set[str],
    ) -> tuple[set[str], set[str], bool]:
        requests: list[tuple[ApprovalGrant, str, str, str, Mapping[str, Any], str]] = []
        consumed_rollback_ids: set[str] = set()
        for step in plan.steps:
            if step.step_id in primary_required:
                grant = approvals.get(step.step_id)
                if grant is None:
                    return set(), set(), False
                requests.append((grant, plan.task_id, trace_id, step.tool, step.arguments, mode.value))
            if step.step_id in rollback_required and step.step_id in rollback_approvals:
                grant = rollback_approvals[step.step_id]
                requests.append((grant, plan.task_id, trace_id, step.rollback_tool or "", step.rollback_arguments, mode.value))
                consumed_rollback_ids.add(step.step_id)
        if not requests:
            # A missing rollback grant must not prevent the primary action from
            # running; the executor will fail closed with ROLLBACK_FAILED if
            # compensation later needs that grant. Primary grants, however,
            # remain mandatory whenever the primary policy requires them.
            return set(), set(), not primary_required
        consume_many = getattr(self.approval_broker, "consume_many", None)
        try:
            consumed = callable(consume_many) and bool(consume_many(requests))
        except Exception:
            consumed = False
        if not consumed:
            return set(), set(), False
        return set(primary_required), consumed_rollback_ids, True

    def _audit(self, trace_id: str, task_id: str, event_type: str, status: str, payload: Mapping[str, Any]) -> None:
        try:
            self.ledger.append_event(trace_id=trace_id, task_id=task_id, event_type=event_type, actor="AdminRuntime", status=status, payload=payload)
        except Exception:
            return


__all__ = ["AdminRuntime", "RuntimeResult"]
