#!/usr/bin/env python3
"""Runner / demo do Live Window Learner (paper-only)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.agent.live_window_learner import LiveWindowLearner


def demo():
    learner = LiveWindowLearner(base_dir=str(ROOT))
    # Simula telemetria minuto a minuto de uma partida
    base = {
        "fixtureId": "demo-1001",
        "home": "Alpha FC",
        "away": "Beta United",
        "stats": {
            "corners": {"home": 2, "away": 1},
            "dangerous": {"home": 18, "away": 14},
        },
        "odds_velocity": 0.02,
        "odds": {"home": 1.85, "draw": 3.4, "away": 4.2},
    }
    for minute in [30, 35, 38, 42, 46, 70, 85, 88, 92]:
        payload = dict(base)
        payload["minute"] = minute
        # simula cantos saindo aos 38 e 90
        if minute >= 38:
            payload["stats"] = {
                "corners": {"home": 3, "away": 2},
                "dangerous": {"home": 22, "away": 16},
            }
        if minute >= 90:
            payload["stats"] = {
                "corners": {"home": 4, "away": 3},
                "dangerous": {"home": 28, "away": 20},
            }
        out = learner.on_telemetry(payload)
        print(f"min={minute} -> {json.dumps(out, ensure_ascii=False)}")

    summary = learner.build_learning_dataset()
    print("SUMMARY", json.dumps(summary, indent=2, ensure_ascii=False))
    print("STATUS", learner.get_status())


if __name__ == "__main__":
    demo()
