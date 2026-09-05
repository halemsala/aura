from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.worker import SystemMonitor
from aura_grid.gpu_sensors import read_gpu0

class ThermalMonitorTests(unittest.TestCase):
    def test_thresholds_from_env(self):
        os.environ["AURA_GRID_MAX_GPU_TEMP_C"] = "72"
        m = SystemMonitor()
        self.assertEqual(m.max_gpu_temp_c, 72.0)

    def test_read_gpu_dict_shape(self):
        g = read_gpu0()
        for k in ("usage", "temp", "mem_temp", "hotspot", "ok"):
            self.assertIn(k, g)

if __name__ == "__main__":
    unittest.main()
