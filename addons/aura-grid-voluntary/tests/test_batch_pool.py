from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.pool_ops import process_batch_item
from concurrent.futures import ProcessPoolExecutor

class BatchPoolTests(unittest.TestCase):
    def test_process_batch_item(self):
        r = process_batch_item({"op": "sha256", "data": {"x": 1}, "id": 7})
        self.assertEqual(r["status"], "SUCCESS")
        self.assertEqual(r["id"], 7)

    def test_pool_map_small(self):
        items = [{"op": "sha256", "data": {"i": i}, "id": i} for i in range(4)]
        with ProcessPoolExecutor(max_workers=2) as pool:
            outs = list(pool.map(process_batch_item, items))
        self.assertEqual(len(outs), 4)
        self.assertTrue(all(o["status"] == "SUCCESS" for o in outs))

if __name__ == "__main__":
    unittest.main()
