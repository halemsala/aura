from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.master import _task_key, MAX_RETRIES

class RetryHelpers(unittest.TestCase):
    def test_task_key_stable(self):
        a = {"op": "sha256", "data": {"x": 1}, "id": 0}
        b = {"op": "sha256", "data": {"x": 1}, "id": 0}
        self.assertEqual(_task_key(a), _task_key(b))

    def test_max_retries_positive(self):
        self.assertGreaterEqual(MAX_RETRIES, 1)

if __name__ == "__main__":
    unittest.main()
