from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.status_registry import StatusRegistry, format_status_table

class StatusTests(unittest.TestCase):
    def test_registry_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "grid_status.json"
            reg = StatusRegistry(p)
            reg.update_worker("127.0.0.1:1", {
                "online": True,
                "cpu_pct": 12,
                "ram_pct": 40,
                "cpu_cores": 8,
                "gpu": {"usage": 55, "temp": 62, "power_w": 120, "power_limit_w": 250, "ok": True},
            })
            reg.set_master(completed_tasks=3)
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(data["worker_count"], 1)
            self.assertEqual(data["workers"][0]["gpu"]["temp"], 62)
            table = format_status_table(data)
            self.assertIn("GPU%", table)
            self.assertIn("TEMP", table)

if __name__ == "__main__":
    unittest.main()
