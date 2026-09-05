from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.ops import run_fixed_op, FIXED_OPS

class OpsTests(unittest.TestCase):
    def test_sha256(self):
        r = run_fixed_op("sha256", {"x": 1})
        self.assertEqual(r["status"], "SUCCESS")
        self.assertIn("digest", r["result"])

    def test_unknown_op_blocked(self):
        r = run_fixed_op("exec_shell", "rm -rf /")
        self.assertEqual(r["status"], "BLOCKED")

    def test_matrix(self):
        r = run_fixed_op("matrix_dot_small", {"a": [[1, 2], [3, 4]], "b": [[5, 6], [7, 8]]})
        self.assertEqual(r["status"], "SUCCESS")
        self.assertEqual(r["result"]["result"], [[19, 22], [43, 50]])

    def test_matrix_too_large(self):
        a = [[0.0] * 40 for _ in range(40)]
        r = run_fixed_op("matrix_dot_small", {"a": a, "b": a})
        self.assertEqual(r["result"]["error"], "matrix_too_large")

    def test_fixed_ops_whitelist(self):
        self.assertNotIn("eval", FIXED_OPS)
        self.assertNotIn("exec", FIXED_OPS)

if __name__ == "__main__":
    unittest.main()
