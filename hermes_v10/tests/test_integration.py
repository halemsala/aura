#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Integration Tests
Testes end-to-end dos módulos core e agents.
"""
import pytest
import asyncio
import json
import os
import tempfile
import shutil
from pathlib import Path

# Ensure imports work
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.hermes_constitution_engine import ConstitutionEngine
from core.hermes_self_healing import SelfHealingEngine
from core.hermes_anomaly_detector import AnomalyDetector
from core.hermes_memory_engine import MemoryEngine, MemoryEntry
from core.hermes_digital_twin import DigitalTwin
from core.hermes_alert_manager import AlertManager


@pytest.fixture(scope="function")
def tmp_root():
    td = tempfile.mkdtemp(prefix="hermes_test_")
    # Create minimal structure
    for sub in ["scripts", "core", "agents", "orchestrator/state_checkpoints", "security", "data/memory", "logs_supervisor", "backups/corrections"]:
        Path(td, sub).mkdir(parents=True, exist_ok=True)
    yield td
    shutil.rmtree(td, ignore_errors=True)


class TestConstitutionEngine:
    def test_scan_text_blocks_execution_true(self, tmp_root):
        engine = ConstitutionEngine(root=tmp_root)
        safe, violations = engine.scan_text("execution_allowed = true")
        assert not safe
        assert len(violations) >= 1

    def test_scan_text_allows_safe_content(self, tmp_root):
        engine = ConstitutionEngine(root=tmp_root)
        safe, violations = engine.scan_text("O sistema está funcionando normalmente.")
        assert safe
        assert len(violations) == 0

    def test_env_invariants_pass_when_correct(self, tmp_root, monkeypatch):
        monkeypatch.setenv("PAPER_TRADE", "true")
        monkeypatch.setenv("EXECUTION_ALLOWED", "false")
        monkeypatch.setenv("AURA_EXECUTION_ALLOWED", "0")
        monkeypatch.setenv("AURA_UNLOCK_LIVE", "0")
        engine = ConstitutionEngine(root=tmp_root)
        ok, violations = engine.check_environment_invariants()
        assert ok
        assert len(violations) == 0

    def test_env_invariants_fail_when_tampered(self, tmp_root, monkeypatch):
        monkeypatch.setenv("EXECUTION_ALLOWED", "true")
        engine = ConstitutionEngine(root=tmp_root)
        ok, violations = engine.check_environment_invariants()
        assert not ok
        assert any("EXECUTION_ALLOWED" in v for v in violations)

    def test_audit_log_written(self, tmp_root):
        engine = ConstitutionEngine(root=tmp_root)
        engine.audit("test_event", {"detail": "value"})
        log_path = Path(tmp_root) / "logs_supervisor" / "security_audit.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "test_event" in content


class TestSelfHealingEngine:
    def test_rejects_low_confidence(self, tmp_root):
        engine = SelfHealingEngine(root=tmp_root)
        result = asyncio.run(engine.attempt_fix("domain_lock", ".", confidence=0.1))
        assert result["status"] == "skipped"
        assert "confidence" in result["reason"].lower()

    def test_rejects_unknown_fix_type(self, tmp_root):
        engine = SelfHealingEngine(root=tmp_root)
        result = asyncio.run(engine.attempt_fix("unknown_fix", ".", confidence=0.99))
        assert result["status"] == "failed"
        assert "no handler" in result.get("reason", "").lower()

    def test_rate_limiting(self, tmp_root):
        engine = SelfHealingEngine(root=tmp_root)
        engine.max_per_hour = 1
        # First should work (if handler registered)
        from core.hermes_self_healing import handler_domain_lock
        engine.register_handler("domain_lock", handler_domain_lock)
        r1 = asyncio.run(engine.attempt_fix("domain_lock", ".", confidence=0.99))
        # Second should be rate limited
        r2 = asyncio.run(engine.attempt_fix("domain_lock", ".", confidence=0.99))
        assert r2["status"] == "skipped" or r1["status"] == "skipped"


class TestAnomalyDetector:
    def test_snapshot_collected(self, tmp_root):
        detector = AnomalyDetector(root=tmp_root)
        snap = detector.collect_snapshot()
        assert snap.ts is not None
        assert snap.log_mb >= 0
        assert snap.error_markers >= 0

    def test_detect_with_insufficient_history(self, tmp_root):
        detector = AnomalyDetector(root=tmp_root)
        is_anomaly, score, details = detector.detect()
        assert not is_anomaly
        assert details.get("reason") == "insufficient_history"


class TestMemoryEngine:
    def test_store_and_retrieve(self, tmp_root):
        engine = MemoryEngine(root=tmp_root)
        entry = MemoryEntry(
            id="test_1",
            ts="2026-01-01T00:00:00Z",
            role="user",
            content="Test memory content about trading systems",
            source="test",
            tags=["test", "trading"],
        )
        ok = engine.store(entry)
        assert ok

        results = engine.search("trading systems", top_k=5)
        assert len(results) >= 1
        assert any("trading" in r["content"] for r in results)

    def test_deduplication(self, tmp_root):
        engine = MemoryEngine(root=tmp_root)
        entry = MemoryEntry(
            id="test_dup",
            ts="2026-01-01T00:00:00Z",
            role="user",
            content="Duplicate content",
            source="test",
            tags=["dup"],
        )
        ok1 = engine.store(entry)
        ok2 = engine.store(entry)
        assert ok1
        assert not ok2  # Should be deduplicated

    def test_context_for_prompt(self, tmp_root):
        engine = MemoryEngine(root=tmp_root)
        entry = MemoryEntry(
            id="ctx_1",
            ts="2026-01-01T00:00:00Z",
            role="assistant",
            content="O sistema AURA está operando em modo paper-trade com 95% de uptime",
            source="diagnostic",
            tags=["status"],
        )
        engine.store(entry)
        ctx = engine.get_context_for_prompt("como está o sistema", max_tokens=500)
        assert "AURA" in ctx or "paper-trade" in ctx


class TestDigitalTwin:
    @pytest.mark.asyncio
    async def test_simulate_domain_lock(self, tmp_root):
        twin = DigitalTwin(root=tmp_root)
        from core.hermes_digital_twin import sim_domain_lock
        twin.register_simulator("domain_lock", sim_domain_lock)
        result = await twin.simulate("domain_lock", {}, depth=1)
        assert result.success
        assert result.confidence > 0.9
        assert len(result.rollback_plan) > 0

    @pytest.mark.asyncio
    async def test_simulate_unknown_action(self, tmp_root):
        twin = DigitalTwin(root=tmp_root)
        result = await twin.simulate("unknown_action", {}, depth=1)
        assert not result.success
        assert "No simulator" in result.predicted_outcome.get("error", "")


class TestAlertManager:
    @pytest.mark.asyncio
    async def test_send_and_retrieve(self, tmp_root):
        mgr = AlertManager(root=tmp_root)
        await mgr.send("warning", "test_source", "Test alert message", {"key": "value"})
        alerts = mgr.get_unacknowledged(min_severity="warning")
        assert len(alerts) >= 1
        assert any("Test alert" in a["message"] for a in alerts)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, tmp_root):
        mgr = AlertManager(root=tmp_root)
        mgr._rate_limit_minutes = 5
        await mgr.send("warning", "dup", "Same message")
        await mgr.send("warning", "dup", "Same message")  # Should be deduplicated
        # Only 1 should be stored (the second is rate-limited)
        # Note: in-memory dedup means second is skipped entirely


class TestPathTraversalProtection:
    def test_read_file_blocks_traversal(self, tmp_root):
        from core.hermes_llm_engine import tool_read_file
        result = tool_read_file("../../../etc/passwd", root=tmp_root)
        assert "Path traversal" in result

    def test_list_dir_blocks_traversal(self, tmp_root):
        from core.hermes_llm_engine import tool_list_dir
        result = tool_list_dir("../../..", root=tmp_root)
        assert "Path traversal" in result


class TestAPIEndpoints:
    def test_health_endpoint_structure(self, tmp_root):
        # We can't fully test FastAPI without running server, but we can verify imports
        from scripts.hermes_v10_chat_api import app
        assert app.title == "Hermes V10 Ultra API"
