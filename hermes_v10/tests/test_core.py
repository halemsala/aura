#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

def test_constitution_blocks_execution_true():
    from hermes_constitution_engine import ConstitutionEngine
    with tempfile.TemporaryDirectory() as td:
        eng = ConstitutionEngine(td)
        ok, viol = eng.validate_action("execution_allowed=TRUE", context="test", agent="test")
        assert ok is False
        assert viol

def test_constitution_env_safe(monkeypatch=None):
    os.environ["PAPER_TRADE"] = "true"
    os.environ["EXECUTION_ALLOWED"] = "false"
    from hermes_constitution_engine import ConstitutionEngine
    with tempfile.TemporaryDirectory() as td:
        eng = ConstitutionEngine(td)
        eng.enforce_env()
        assert os.environ["EXECUTION_ALLOWED"].lower() == "false"

def test_path_traversal_blocked():
    from hermes_llm_engine import ToolRegistry
    with tempfile.TemporaryDirectory() as td:
        Path(td, "ok.txt").write_text("x", encoding="utf-8")
        reg = ToolRegistry(Path(td))
        bad = reg.read_file(path="../../../etc/passwd")
        assert "inválido" in bad or "error" in bad.lower() or "ok\": false" in bad.replace(" ", "")

def test_event_bus_wal():
    from hermes_event_bus import EventBus
    with tempfile.TemporaryDirectory() as td:
        bus = EventBus(str(Path(td) / "e.db"))
        eid = bus.publish("t", {"a": 1})
        assert eid >= 1
        assert bus.recent(5)

def test_anomaly_runs():
    from hermes_anomaly_detector import AnomalyDetector
    with tempfile.TemporaryDirectory() as td:
        d = AnomalyDetector(td)
        d.fit()
        r = d.check()
        assert "score" in r
        assert "model" in r

if __name__ == "__main__":
    test_constitution_blocks_execution_true()
    test_constitution_env_safe()
    test_path_traversal_blocked()
    test_event_bus_wal()
    test_anomaly_runs()
    print("ALL_TESTS_OK")
