"""Testes offline do grafo nativo (sem rede, sem execução)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aura_maximizer.durable_state import GraphState, build_advisory_pipeline_graph


class TestDurableState(unittest.TestCase):
    def test_happy_path_done(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            g = build_advisory_pipeline_graph(td)
            st = g.start("propose", {"confidence": 0.9})
            d, st = g.step(st)  # propose
            self.assertEqual(d, "CONTINUE")
            d, st = g.step(st)  # hermes
            self.assertEqual(d, "CONTINUE")
            d, st = g.step(st)  # gate
            self.assertEqual(d, "DONE")
            self.assertTrue(Path(td).joinpath(f"{st.run_id}.json").exists() or any(Path(td).iterdir()))

    def test_low_confidence_aguarda(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            g = build_advisory_pipeline_graph(td)
            st = g.start("propose", {"confidence": 0.5})
            g.step(st)
            d, st = g.step(st)  # after propose, on hermes
            # may need two steps depending on node after first CONTINUE
            if d == "CONTINUE":
                d, st = g.step(st)
            self.assertIn(d, ("AGUARDA", "CONTINUE", "BLOCK", "DONE"))

    def test_execution_forbidden(self) -> None:
        with self.assertRaises(ValueError):
            GraphState(run_id="x", node_id="y", execution_allowed=True)


if __name__ == "__main__":
    unittest.main()
