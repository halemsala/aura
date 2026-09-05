"""AURA administrator control plane.

The GLM proposes structured plans. This module validates them through the
canonical policy gate and executes only allowlisted, audited actions after an
explicit, digest-bound human approval. It deliberately exposes no arbitrary
shell, filesystem path, credential, network, or real-order tool.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import socket
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from scripts.aura_admin_core import (
    AdminPlan,
    AutonomyMode,
    AuditLedger,
    DecisionStatus,
    DAGPlanExecutor,
    GLMPlanner,
    PlanStep,
    PlanVerifier,
    PolicyGate,
    RiskLevel,
    ToolManifest,
    ToolRegistry,
)
from scripts.aura_admin_governance import ApprovalBroker, ApprovalGrant, CircuitBreaker, ContextBuilder, PostconditionVerifier
from scripts.aura_admin_config import load_config


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "aura-admin-config.json"
CHECKPOINT_ROOT = ROOT / "runtime" / "checkpoints"
CHECKPOINT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
MODEL = os.getenv("CORNERAI_ADMIN_MODEL", os.getenv("CORNERAI_CHAT_MODEL", "llama3.2:3b"))
OLLAMA_HOST = os.getenv("CORNERAI_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# This allowlist is intentionally small. New mutation tools must be added as a
# reviewed manifest plus a deterministic executor and rollback contract.
CHECKPOINT_FILES = (
    "config/aura-admin-config.json",
    "AURA_INSTALAR_E_INICIAR_TUDO.bat",
    "AURA_INICIAR_SISTEMA.bat",
    "engine/server.py",
    "engine/orchestrator.py",
    "engine/admin/aura_admin_api.py",
    "engine/agent_glm_runtime.py",
    "engine/agent_registry.py",
    "bridge/jarvis/config.yaml",
    "bridge/jarvis_voice_server.py",
    "bridge/jarvis/modules/neural_tts.py",
    "scripts/activate_reference_voice.py",
    "AURA_ATIVAR_VOZ_REFERENCIA.bat",
    "AURA_RESTAURAR_VOZ_EDGE.bat",
    "desktop/Models.cs",
    "desktop/config/desktop.json",
    "desktop/ui/app.js",
    "desktop/ui/styles.css",
)
LOG_FILES = {
    "bridge": ROOT / "bridge" / "runtime_bridge.log",
    "engine": ROOT / "engine" / "runtime_engine.log",
    "voice": ROOT / "bridge" / "runtime_voice.log",
    "installer": ROOT / "logs_instalacao" / "desktop_host.log",
}
SERVICE_URLS = {
    "bridge": "http://127.0.0.1:8080/health",
    "engine": "http://127.0.0.1:8765/api/health",
    "voice": "http://127.0.0.1:8099/api/voice/health",
    "ollama": f"{OLLAMA_HOST}/api/tags",
}


class OllamaStructuredAdapter:
    """Small Ollama adapter returning only the model's structured text."""

    def complete(self, *, messages: list[dict[str, Any]], response_schema: dict[str, Any], timeout_s: float) -> str:
        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": -1,
            "options": {"temperature": 0.0, "num_predict": 1_600, "num_ctx": 4_096, "num_gpu": 99},
        }
        request = urllib.request.Request(
            f"{OLLAMA_HOST}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "AURA-Admin/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(2.0, float(timeout_s))) as response:
                document = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            raise RuntimeError(f"ollama_adapter_unavailable:{type(exc).__name__}") from exc
        message = document.get("message") if isinstance(document, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not content:
            content = document.get("response") if isinstance(document, Mapping) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("ollama returned an empty structured response")
        return content


def _schema(properties: Mapping[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties), "required": required, "additionalProperties": False}


def _manifest(
    name: str,
    description: str,
    properties: Mapping[str, Any],
    required: list[str],
    *,
    risk: RiskLevel = RiskLevel.LOW,
    modes: tuple[AutonomyMode, ...] = (
        AutonomyMode.OBSERVE,
        AutonomyMode.PLAN_ONLY,
        AutonomyMode.DRY_RUN,
        AutonomyMode.SUPERVISED,
        AutonomyMode.GUARDED_AUTONOMY,
    ),
    side_effects: tuple[str, ...] = (),
    rollback: str = "not_applicable_read_only",
    rollback_tool: str | None = None,
    requires_approval: bool = False,
) -> ToolManifest:
    return ToolManifest.from_dict(
        {
            "name": name,
            "version": "1.0.0",
            "description": description,
            "risk_level": risk.value,
            "input_schema": _schema(properties, required),
            "output_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "allowed_agents": ["aura-admin"],
            "allowed_modes": [item.value for item in modes],
            "side_effects": list(side_effects),
            "timeout_s": 30,
            "idempotency": "keyed" if side_effects else "idempotent",
            "rollback": rollback,
            "rollback_tool": rollback_tool,
            "requires_approval": requires_approval,
            "audit_events": ["tool_requested", "tool_completed", "tool_rejected"],
        }
    )


def _build_registry() -> ToolRegistry:
    all_modes = (
        AutonomyMode.OBSERVE,
        AutonomyMode.PLAN_ONLY,
        AutonomyMode.DRY_RUN,
        AutonomyMode.SUPERVISED,
        AutonomyMode.GUARDED_AUTONOMY,
    )
    return ToolRegistry(
        [
            _manifest(
                "read_health",
                "Read one canonical AURA service health endpoint without side effects.",
                {"service": {"type": "string", "enum": ["bridge", "engine", "voice", "ollama"]}},
                ["service"],
            ),
            _manifest("read_agents", "Read the canonical registered-agent catalog without executing agents.", {}, []),
            _manifest(
                "read_agent_health",
                "Read a registered agent health state without executing its functions.",
                {"agent_id": {"type": "string", "minLength": 1, "maxLength": 160}},
                ["agent_id"],
            ),
            _manifest(
                "read_recent_logs",
                "Read a bounded, redacted tail of one canonical AURA log.",
                {"service": {"type": "string", "enum": ["bridge", "engine", "voice", "installer"]}, "lines": {"type": "integer"}},
                ["service", "lines"],
            ),
            _manifest("read_audit_health", "Read the hash-chain audit ledger health.", {}, []),
            _manifest("read_ports", "Probe the four canonical local service ports without side effects.", {}, []),
            _manifest(
                "list_checkpoints",
                "List immutable local AURA checkpoints without modifying them.",
                {},
                [],
            ),
            _manifest(
                "create_checkpoint",
                "Create an allowlisted configuration checkpoint before a supervised change.",
                {"label": {"type": "string", "minLength": 1, "maxLength": 120}},
                ["label"],
                risk=RiskLevel.MEDIUM,
                modes=all_modes,
                side_effects=("checkpoint_write",),
                rollback="restore_the_created_checkpoint_if_a_following_step_fails",
                rollback_tool="restore_checkpoint",
                requires_approval=True,
            ),
            _manifest(
                "restore_checkpoint",
                "Restore one previously created allowlisted checkpoint.",
                {"checkpoint_id": {"type": "string", "minLength": 1, "maxLength": 80}},
                ["checkpoint_id"],
                risk=RiskLevel.HIGH,
                modes=(AutonomyMode.SUPERVISED,),
                side_effects=("allowlisted_file_restore",),
                rollback="create_a_new_checkpoint_before_restore",
                rollback_tool="create_checkpoint",
                requires_approval=True,
            ),
            _manifest(
                "set_autonomy_mode",
                "Change only the administrative autonomy mode; PAPER TRADE remains immutable.",
                {"mode": {"type": "string", "enum": [item.value for item in AutonomyMode]}},
                ["mode"],
                risk=RiskLevel.HIGH,
                modes=(AutonomyMode.SUPERVISED,),
                side_effects=("admin_config_write",),
                rollback="restore_the_previous_autonomy_mode",
                rollback_tool="set_autonomy_mode",
                requires_approval=True,
            ),
        ]
    )


class AdminExecutor:
    def __init__(self, ledger: AuditLedger) -> None:
        self.ledger = ledger

    @staticmethod
    def _bounded_lines(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("lines must be an integer")
        return max(1, min(value, 200))

    def execute(self, step: PlanStep) -> Mapping[str, Any]:
        started = time.time()
        result: Mapping[str, Any]
        if step.tool == "read_health":
            result = self._read_health(str(step.arguments["service"]))
        elif step.tool == "read_agents":
            result = self._read_agents()
        elif step.tool == "read_agent_health":
            result = self._read_agent_health(str(step.arguments["agent_id"]))
        elif step.tool == "read_recent_logs":
            result = self._read_recent_logs(str(step.arguments["service"]), self._bounded_lines(step.arguments["lines"]))
        elif step.tool == "read_audit_health":
            result = {"ok": True, "status": "PASS_RUNTIME", "evidence": self.ledger.health()}
        elif step.tool == "read_ports":
            result = self._read_ports()
        elif step.tool == "list_checkpoints":
            result = {"ok": True, "checkpoints": self._list_checkpoints()}
        elif step.tool == "create_checkpoint":
            result = self._create_checkpoint(str(step.arguments["label"]))
        elif step.tool == "restore_checkpoint":
            result = self._restore_checkpoint(str(step.arguments["checkpoint_id"]))
        elif step.tool == "set_autonomy_mode":
            result = self._set_autonomy_mode(str(step.arguments["mode"]))
        else:
            raise ValueError(f"tool not implemented by deterministic executor: {step.tool}")
        finished = time.time()
        return {
            "ok": bool(result.get("ok", True)),
            "status": result.get("status", "PASS_RUNTIME"),
            "evidence": dict(result),
            "started_at": started,
            "finished_at": finished,
            "trace_id": str(uuid.uuid4()),
        }

    def rollback(self, step: PlanStep, execution_result: Mapping[str, Any]) -> Mapping[str, Any]:
        tool = step.rollback_tool
        arguments = dict(step.rollback_arguments or {})
        if tool == "restore_checkpoint":
            checkpoint_id = str(arguments.get("checkpoint_id") or ((execution_result.get("evidence") or {}).get("checkpoint_id")) or "")
            if not checkpoint_id:
                raise ValueError("rollback checkpoint_id is missing")
            return self._restore_checkpoint(checkpoint_id)
        if tool == "create_checkpoint":
            return self._create_checkpoint("rollback-before-restore")
        if tool == "set_autonomy_mode":
            previous = str(arguments.get("mode") or ((execution_result.get("evidence") or {}).get("previous_mode")) or "")
            if not previous:
                raise ValueError("rollback mode is missing")
            return self._set_autonomy_mode(previous)
        raise ValueError(f"rollback tool not implemented: {tool}")

    def _read_health(self, service: str) -> Mapping[str, Any]:
        url = SERVICE_URLS.get(service)
        if not url:
            raise ValueError("unknown service")
        started = time.time()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AURA-Admin/1.0"})
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read(8_000).decode("utf-8", errors="replace")
            return {"ok": True, "service": service, "status": "PASS_RUNTIME", "http_status": int(response.status), "payload": json.loads(body), "latency_ms": round((time.time() - started) * 1000, 2)}
        except Exception as exc:
            return {"ok": False, "service": service, "status": "BLOCKED", "error": type(exc).__name__}

    @staticmethod
    def _read_agents() -> Mapping[str, Any]:
        try:
            try:
                from agent_registry import catalog
            except ImportError:
                from engine.agent_registry import catalog
            catalog_data = catalog()
            return {"ok": True, "status": "PASS_RUNTIME", "count": catalog_data.get("count", 0), "declared_count": catalog_data.get("declaredCount", 0), "agents": catalog_data.get("agents", [])}
        except Exception as exc:
            return {"ok": False, "status": "BLOCKED", "error": type(exc).__name__}

    @staticmethod
    def _read_agent_health(agent_id: str) -> Mapping[str, Any]:
        try:
            try:
                from agent_registry import action
            except ImportError:
                from engine.agent_registry import action
            data = action(agent_id, "health", {})
            return {"ok": bool(data.get("ok")), "status": "PASS_RUNTIME" if data.get("ok") else "WARNING", "agent": data}
        except Exception as exc:
            return {"ok": False, "status": "BLOCKED", "error": type(exc).__name__}

    @staticmethod
    def _read_recent_logs(service: str, lines: int) -> Mapping[str, Any]:
        path = LOG_FILES.get(service)
        if path is None:
            raise ValueError("unknown log service")
        if not path.is_file():
            return {"ok": False, "status": "WARNING", "path": str(path.relative_to(ROOT)), "message": "log ausente"}
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        redacted = "\n".join(_redact_line(line) for line in content)
        return {"ok": True, "status": "PASS_RUNTIME", "path": str(path.relative_to(ROOT)), "lines": len(content), "content": redacted[:32_000]}

    @staticmethod
    def _read_ports() -> Mapping[str, Any]:
        ports = {"bridge": 8080, "engine": 8765, "voice": 8099, "ollama": 11434}
        states: dict[str, Any] = {}
        for name, port in ports.items():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.7):
                    states[name] = {"port": port, "open": True}
            except OSError:
                states[name] = {"port": port, "open": False}
        return {"ok": True, "status": "PASS_RUNTIME", "ports": states}

    @staticmethod
    def _checkpoint_path(checkpoint_id: str) -> Path:
        if not CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
            raise ValueError("invalid checkpoint_id")
        path = (CHECKPOINT_ROOT / checkpoint_id).resolve()
        if CHECKPOINT_ROOT.resolve() not in path.parents:
            raise ValueError("checkpoint path escapes allowed directory")
        return path

    def _list_checkpoints(self) -> list[dict[str, Any]]:
        if not CHECKPOINT_ROOT.is_dir():
            return []
        output: list[dict[str, Any]] = []
        for path in sorted(CHECKPOINT_ROOT.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if path.is_dir() and CHECKPOINT_ID_RE.fullmatch(path.name):
                metadata = path / "metadata.json"
                try:
                    data = json.loads(metadata.read_text(encoding="utf-8")) if metadata.is_file() else {}
                except Exception:
                    data = {}
                output.append({"checkpoint_id": path.name, **{key: data.get(key) for key in ("label", "created_at", "files")}})
        return output[:100]

    def _create_checkpoint(self, label: str) -> Mapping[str, Any]:
        label = label.strip()[:120]
        if not label:
            raise ValueError("checkpoint label is required")
        CHECKPOINT_ROOT.mkdir(parents=True, exist_ok=True)
        checkpoint_id = f"cp_{time.strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
        target = self._checkpoint_path(checkpoint_id)
        target.mkdir(parents=True, exist_ok=False)
        copied: list[str] = []
        for relative in CHECKPOINT_FILES:
            source = ROOT / relative
            if not source.is_file():
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
        metadata = {"checkpoint_id": checkpoint_id, "label": label, "created_at": time.time(), "files": copied, "paper_trade_only": True}
        (target / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "status": "PASS_RUNTIME", "checkpoint_id": checkpoint_id, "label": label, "files": copied}

    def _restore_checkpoint(self, checkpoint_id: str) -> Mapping[str, Any]:
        source_root = self._checkpoint_path(checkpoint_id)
        metadata_path = source_root / "metadata.json"
        if not metadata_path.is_file():
            raise ValueError("checkpoint not found or metadata missing")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        pre_restore = self._create_checkpoint(f"before-restore-{checkpoint_id}")
        restored: list[str] = []
        for relative in metadata.get("files", []):
            if relative not in CHECKPOINT_FILES:
                raise ValueError("checkpoint contains a file outside the allowlist")
            source = source_root / relative
            destination = ROOT / relative
            if not source.is_file():
                raise ValueError(f"checkpoint file missing: {relative}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored.append(relative)
        return {"ok": True, "status": "PASS_RUNTIME", "checkpoint_id": checkpoint_id, "pre_restore_checkpoint": pre_restore.get("checkpoint_id"), "restored": restored}

    def _set_autonomy_mode(self, mode: str) -> Mapping[str, Any]:
        try:
            selected = AutonomyMode(mode)
        except ValueError as exc:
            raise ValueError("invalid autonomy mode") from exc
        if not CONFIG_PATH.is_file():
            raise ValueError("admin config missing")
        checkpoint = self._create_checkpoint(f"before-mode-{selected.value.lower()}")
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        previous = str(raw.get("mode") or AutonomyMode.PLAN_ONLY.value)
        raw["mode"] = selected.value
        raw["paper_trade_only"] = True
        validated = load_config(raw)
        CONFIG_PATH.write_text(json.dumps(validated.public_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "status": "PASS_RUNTIME", "previous_mode": previous, "mode": selected.value, "paper_trade_only": True, "pre_change_checkpoint": checkpoint.get("checkpoint_id")}


def _redact_line(value: str) -> str:
    from scripts.aura_admin_core import RiskAnalyzer
    return RiskAnalyzer.redact(value)[:2_000]


def _plan_to_dict(plan: AdminPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "task_id": plan.task_id,
        "goal": plan.goal,
        "assumptions": list(plan.assumptions),
        "steps": [
            {
                "step_id": step.step_id,
                "tool": step.tool,
                "arguments": step.arguments,
                "reason": step.reason,
                "risk_level": step.risk_level.value,
                "requires_approval": step.requires_approval,
                "expected": step.expected,
                "depends_on": list(step.depends_on),
                "rollback_tool": step.rollback_tool,
                "rollback_arguments": step.rollback_arguments,
            }
            for step in plan.steps
        ],
        "stop_conditions": list(plan.stop_conditions),
        "evidence_requirements": list(plan.evidence_requirements),
        "execution_order": list(plan.execution_order),
        "rollback_order": list(plan.rollback_order),
        "fingerprint": plan.fingerprint(),
    }


class PlanRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2_000)
    context: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = Field(default=None, max_length=256)
    mode: str = Field(default="PLAN_ONLY")


class ApprovalRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=256)
    trace_id: str = Field(min_length=1, max_length=256)
    step_id: str = Field(pattern=r"^s[0-9]+$")
    approver: str = Field(min_length=1, max_length=120)
    ttl_s: float = Field(default=300.0, gt=0, le=3_600)


class ExecuteRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=256)
    trace_id: str = Field(min_length=1, max_length=256)
    mode: str = Field(default="SUPERVISED")
    approvals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rollback_approvals: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentActionRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    mode: str = Field(default="OBSERVE")


_LOCK = RLock()
_PLANS: dict[tuple[str, str], AdminPlan] = {}
_BROKER = ApprovalBroker(secrets.token_bytes(32), default_ttl_s=300.0)
_LEDGER = AuditLedger(ROOT / "engine" / "aura_quant_x.db")
_LEDGER.initialize()
_REGISTRY = _build_registry()
_GATE = PolicyGate(_REGISTRY, audit_ledger=_LEDGER)
try:
    _GATE.set_mode_ceiling(load_config(CONFIG_PATH).mode)
except Exception:
    # Sem config válida, a produção começa no teto mínimo e os endpoints
    # continuam respondendo CONFIG_INVALID/503 até a correção explícita.
    _GATE.set_mode_ceiling(AutonomyMode.PLAN_ONLY)
_VERIFIER = PlanVerifier(_GATE, max_steps=32)
_PLANNER = GLMPlanner(
    OllamaStructuredAdapter(),
    _VERIFIER,
    timeout_s=30.0,
    audit_ledger=_LEDGER,
    max_context_chars=32_000,
)
_EXECUTOR = AdminExecutor(_LEDGER)
_DAG = DAGPlanExecutor(_GATE, _LEDGER, postcondition_verifier=PostconditionVerifier())
_ADMIN_TOKEN_ENV = "AURA_ADMIN_TOKEN"
_APPROVER_TOKEN_ENV = "AURA_ADMIN_APPROVER_TOKEN"
_APPROVER_ID_ENV = "AURA_ADMIN_APPROVER_ID"
_MODE_ORDER = {
    AutonomyMode.DISABLED: 0,
    AutonomyMode.OBSERVE: 1,
    AutonomyMode.PLAN_ONLY: 2,
    AutonomyMode.DRY_RUN: 3,
    AutonomyMode.SUPERVISED: 4,
    AutonomyMode.GUARDED_AUTONOMY: 5,
}


def _configured_token(name: str) -> str:
    return os.getenv(name, "").strip()


def _bearer(request: Request) -> str:
    value = request.headers.get("Authorization", "").strip()
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _require_admin_auth(request: Request) -> None:
    expected = _configured_token(_ADMIN_TOKEN_ENV)
    if not expected:
        raise HTTPException(status_code=503, detail="admin_auth_not_configured")
    supplied = _bearer(request)
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="admin_auth_required")


def _require_approver_auth(request: Request) -> None:
    _require_admin_auth(request)
    expected = _configured_token(_APPROVER_TOKEN_ENV)
    if not expected or hmac.compare_digest(expected, _configured_token(_ADMIN_TOKEN_ENV)):
        raise HTTPException(status_code=503, detail="separate_approver_auth_not_configured")
    approver_id = _configured_token(_APPROVER_ID_ENV)
    if not approver_id:
        raise HTTPException(status_code=503, detail="approver_identity_not_configured")
    supplied = request.headers.get("X-AURA-Approver-Token", "").strip()
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="approver_auth_required")


def _runtime_config_or_503():
    try:
        config = load_config(CONFIG_PATH)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "CONFIG_INVALID", "error": type(exc).__name__}) from None
    _GATE.set_mode_ceiling(config.mode)
    return config


def _enforce_mode_ceiling(mode: AutonomyMode):
    config = _runtime_config_or_503()
    if _MODE_ORDER[mode] > _MODE_ORDER[config.mode]:
        raise HTTPException(status_code=403, detail={"status": "MODE_CEILING_BLOCKED", "requested_mode": mode.value, "configured_mode": config.mode.value})
    return config


_ROUTER = APIRouter(prefix="/api/admin", tags=["aura-admin"], dependencies=[Depends(_require_admin_auth)])


def _config_public() -> dict[str, Any]:
    try:
        config = load_config(CONFIG_PATH)
        _GATE.set_mode_ceiling(config.mode)
        return config.public_dict()
    except Exception as exc:
        return {"mode": AutonomyMode.PLAN_ONLY.value, "paper_trade_only": True, "status": "DEGRADED", "error": type(exc).__name__}


@_ROUTER.get("/health")
def admin_health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "aura-admin-control-plane",
        "mode": _config_public().get("mode", AutonomyMode.PLAN_ONLY.value),
        "paper_trade_only": True,
        "glm": {"provider": "ollama", "model": MODEL, "host": OLLAMA_HOST},
        "tools": list(_REGISTRY.names()),
        "ledger": _LEDGER.health(),
        "architecture": {"planner_proposes": True, "policy_gate_validates": True, "human_approval_required_for_mutation": True, "arbitrary_shell": False, "real_orders": False},
    }


@_ROUTER.get("/tools")
def admin_tools() -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    for name in _REGISTRY.names():
        manifest = _REGISTRY.get(name)
        if manifest is None:
            continue
        manifests.append({"name": manifest.name, "version": manifest.version, "description": manifest.description, "risk_level": manifest.risk_level.value, "allowed_modes": [item.value for item in manifest.allowed_modes], "side_effects": list(manifest.side_effects), "requires_approval": manifest.requires_approval, "fingerprint": manifest.fingerprint()})
    return {"ok": True, "tools": manifests, "paper_trade_only": True}


@_ROUTER.get("/config")
def admin_config() -> dict[str, Any]:
    return {"ok": True, "config": _config_public(), "paper_trade_only": True}


@_ROUTER.get("/history")
def admin_history(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    return {"ok": True, "episodes": _LEDGER.recent_episodes(limit=limit), "ledger": _LEDGER.health()}


@_ROUTER.get("/events/{trace_id}")
def admin_events(trace_id: str) -> dict[str, Any]:
    return {"ok": True, "trace_id": trace_id, "events": _LEDGER.trace_events(trace_id)}


@_ROUTER.get("/checkpoints")
def admin_checkpoints() -> dict[str, Any]:
    return {"ok": True, "checkpoints": _EXECUTOR._list_checkpoints(), "allowlist": list(CHECKPOINT_FILES)}


@_ROUTER.post("/plan")
def admin_plan(request: PlanRequest) -> dict[str, Any]:
    try:
        mode = AutonomyMode(request.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid autonomy mode") from None
    _enforce_mode_ceiling(mode)
    task_id = request.task_id or f"admin-{uuid.uuid4()}"
    context = dict(request.context)
    context.setdefault("runtime", {"config": _config_public(), "ledger": _LEDGER.health(), "tools": list(_REGISTRY.names())})
    trace_id = str(uuid.uuid4())
    try:
        messages = _PLANNER.plan(task_id=task_id, goal=request.goal, context=context, agent="aura-admin", mode=mode, trace_id=trace_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail={"status": "GLM_UNAVAILABLE", "error": type(exc).__name__, "trace_id": trace_id}) from None
    plan = messages.verification.plan
    if plan is None:
        _LEDGER.append_event(trace_id=messages.trace_id, task_id=task_id, event_type="plan_rejected", actor="GLMPlanner", status="PLAN_INVALID", payload={"error_code": messages.error_code, "errors": list(messages.verification.errors)}, idempotency_key=f"{messages.trace_id}:plan_rejected")
        return {"ok": False, "status": "PLAN_INVALID", "trace_id": messages.trace_id, "error_code": messages.error_code, "errors": list(messages.verification.errors), "warnings": list(messages.verification.warnings), "required_approvals": list(messages.verification.required_approvals), "latency_ms": messages.latency_ms}
    with _LOCK:
        _PLANS[(task_id, messages.trace_id)] = plan
    event_id = _LEDGER.append_event(trace_id=messages.trace_id, task_id=task_id, event_type="plan_ready", actor="GLMPlanner", status="PLAN_READY", payload={"goal": request.goal, "mode": mode.value, "plan_hash": plan.fingerprint(), "required_approvals": list(messages.verification.required_approvals)}, idempotency_key=f"{messages.trace_id}:plan_ready")
    try:
        _LEDGER.remember_episode(task_id=task_id, episode_type="admin_plan", summary=request.goal[:2_000], status="PLANNED", source_event_id=event_id, metadata={"trace_id": messages.trace_id, "plan_hash": plan.fingerprint(), "mode": mode.value})
    except Exception:
        pass
    return {"ok": True, "status": "PLAN_READY", "trace_id": messages.trace_id, "task_id": task_id, "mode": mode.value, "plan": _plan_to_dict(plan), "required_approvals": list(messages.verification.required_approvals), "latency_ms": messages.latency_ms}


@_ROUTER.post("/approve", dependencies=[Depends(_require_approver_auth)])
def admin_approve(request: ApprovalRequest) -> dict[str, Any]:
    if request.approver != _configured_token(_APPROVER_ID_ENV):
        raise HTTPException(status_code=403, detail="approver_identity_mismatch")
    with _LOCK:
        plan = _PLANS.get((request.task_id, request.trace_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found or expired from runtime memory")
    step = next((item for item in plan.steps if item.step_id == request.step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail="step not found")
    try:
        mode = AutonomyMode.SUPERVISED
        grant = _BROKER.issue(task_id=plan.task_id, trace_id=request.trace_id, tool=step.tool, arguments=step.arguments, mode=mode.value, approver=request.approver, ttl_s=request.ttl_s)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"approval rejected: {type(exc).__name__}") from None
    _LEDGER.append_event(trace_id=request.trace_id, task_id=plan.task_id, event_type="approval_issued", actor=request.approver, status="APPROVED", payload={"step_id": step.step_id, "tool": step.tool, "expires_at": grant.expires_at}, idempotency_key=f"{grant.grant_id}:approval")
    return {"ok": True, "status": "APPROVAL_ISSUED", "step_id": step.step_id, "grant": asdict(grant), "plan_fingerprint": plan.fingerprint(), "expires_at": grant.expires_at}


@_ROUTER.post("/agent-action")
def admin_agent_action(request: AgentActionRequest) -> dict[str, Any]:
    safe_actions = {"status", "inspect", "health", "pending", "voice_diagnostic", "paper_preview", "simulation_contract"}
    if request.action not in safe_actions:
        raise HTTPException(status_code=403, detail="agent action is not read-only allowlisted")
    if request.mode != AutonomyMode.OBSERVE.value:
        raise HTTPException(status_code=400, detail="read-only agent actions must use OBSERVE mode")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", request.agent_id):
        raise HTTPException(status_code=400, detail="invalid agent_id")
    try:
        try:
            from agent_registry import action
        except ImportError:
            from engine.agent_registry import action
        result = action(request.agent_id, request.action, dict(request.payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"agent action failed: {type(exc).__name__}") from None
    trace_id = str(uuid.uuid4())
    status_value = "PASS" if result.get("ok", False) else "WARNING"
    _LEDGER.append_event(trace_id=trace_id, task_id=None, event_type="agent_action", actor="aura-admin", status=status_value, payload={"agent_id": request.agent_id, "action": request.action, "result": result})
    return {"ok": bool(result.get("ok")), "status": status_value, "trace_id": trace_id, "agent_id": request.agent_id, "action": request.action, "result": result, "paper_trade_only": True}


@_ROUTER.post("/execute")
def admin_execute(request: ExecuteRequest) -> dict[str, Any]:
    try:
        mode = AutonomyMode(request.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid autonomy mode") from None
    _enforce_mode_ceiling(mode)
    if mode is not AutonomyMode.SUPERVISED:
        raise HTTPException(status_code=400, detail="mutating execution is available only in SUPERVISED mode")
    with _LOCK:
        plan = _PLANS.get((request.task_id, request.trace_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="plan not found or expired from runtime memory")
    grants: dict[str, ApprovalGrant] = {}
    rollback_grants: dict[str, ApprovalGrant] = {}
    for step_id, raw in request.approvals.items():
        try:
            grants[step_id] = ApprovalGrant(**raw)
        except Exception:
            raise HTTPException(status_code=400, detail=f"invalid approval grant for {step_id}") from None
    for step_id, raw in request.rollback_approvals.items():
        try:
            rollback_grants[step_id] = ApprovalGrant(**raw)
        except Exception:
            raise HTTPException(status_code=400, detail=f"invalid rollback approval grant for {step_id}") from None
    approved: list[str] = []
    rollback_approved: list[str] = []
    missing: list[str] = []
    grant_requests: list[tuple[ApprovalGrant, str, str, str, Mapping[str, Any], str]] = []
    rollback_requests: list[tuple[ApprovalGrant, str, str, str, Mapping[str, Any], str]] = []
    for step in plan.steps:
        decision = _GATE.decide(step.tool, step.arguments, agent="aura-admin", mode=mode, trace_id=request.trace_id, approval_granted=False)
        if decision.status is DecisionStatus.DENY:
            raise HTTPException(status_code=403, detail={"status": "BLOCKED", "step_id": step.step_id, "reason": decision.reason})
        if decision.status is DecisionStatus.REQUIRE_APPROVAL:
            grant = grants.get(step.step_id)
            if grant is None or not _BROKER.validate(grant, task_id=plan.task_id, trace_id=request.trace_id, tool=step.tool, arguments=step.arguments, mode=mode.value):
                missing.append(step.step_id)
            else:
                approved.append(step.step_id)
                grant_requests.append((grant, plan.task_id, request.trace_id, step.tool, step.arguments, mode.value))
        if step.rollback_tool:
            rollback_decision = _GATE.decide(step.rollback_tool, step.rollback_arguments, agent="aura-admin", mode=mode, trace_id=request.trace_id, approval_granted=False, for_planning=True)
            if rollback_decision.status is DecisionStatus.DENY:
                raise HTTPException(status_code=403, detail={"status": "ROLLBACK_BLOCKED", "step_id": step.step_id, "reason": rollback_decision.reason})
            if rollback_decision.status is DecisionStatus.REQUIRE_APPROVAL:
                rollback_grant = rollback_grants.get(step.step_id)
                if rollback_grant is None or not _BROKER.validate(rollback_grant, task_id=plan.task_id, trace_id=request.trace_id, tool=step.rollback_tool, arguments=step.rollback_arguments, mode=mode.value):
                    missing.append(f"rollback:{step.step_id}")
                else:
                    rollback_approved.append(step.step_id)
                    rollback_requests.append((rollback_grant, plan.task_id, request.trace_id, step.rollback_tool, step.rollback_arguments, mode.value))
    if missing:
        return {"ok": False, "status": "APPROVAL_REQUIRED", "trace_id": request.trace_id, "missing_steps": missing, "message": "Nenhuma alteração foi executada; aprove cada passo indicado e envie os grants novamente."}
    all_requests = grant_requests + rollback_requests
    if all_requests and not _BROKER.consume_many(all_requests):
        return {"ok": False, "status": "APPROVAL_REQUIRED", "trace_id": request.trace_id, "missing_steps": ["grant_consume_failed"], "message": "As aprovações não puderam ser consumidas atomicamente; nenhuma alteração foi executada."}
    try:
        execution = _DAG.run(plan, agent="aura-admin", mode=mode, executor=_EXECUTOR, approval_granted_steps=tuple(approved), rollback_approval_granted_steps=tuple(rollback_approved), trace_id=request.trace_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"status": "FAILED", "error": type(exc).__name__}) from None
    return {"ok": execution.status in {"COMPLETED", "ROLLED_BACK"}, "status": execution.status, "trace_id": execution.trace_id, "execution_order": list(execution.execution_order), "completed": list(execution.completed), "failed_step": execution.failed_step, "rollback_completed": list(execution.rollback_completed), "errors": list(execution.errors), "latency_ms": execution.latency_ms, "paper_trade_only": True}


router = _ROUTER
__all__ = ["router"]
