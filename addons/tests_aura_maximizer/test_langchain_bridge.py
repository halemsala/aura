"""Testes da ponte LangChain (sem exigir langchain instalado)."""
from __future__ import annotations

import unittest

from aura_maximizer.langchain_bridge import (
    AURALangChainToolGuard,
    AURARunnablePipeline,
    build_aura_langchain_chain,
    langchain_available,
)


class LangChainBridgeTests(unittest.TestCase):
    def test_invoke_ralph_offline(self):
        pipe = AURARunnablePipeline(mode="ralph")
        out = pipe.invoke(
            {
                "task_id": "t-lc-1",
                "snapshot": {"sources": ["dom", "feed"], "fixture_id": "fx1"},
            }
        )
        self.assertIn(out["decision"], {"ADVISORY", "AGUARDA", "BLOCK"})
        self.assertFalse(out["execution_allowed"])
        self.assertTrue(out["paper_trade"])
        self.assertEqual(out["task_id"], "t-lc-1")
        self.assertIn("langchain_core_available", out)

    def test_invoke_tot(self):
        pipe = AURARunnablePipeline(mode="tot")
        out = pipe.invoke({"task_id": "t-tot", "snapshot": {"sources": ["a", "b"]}})
        self.assertFalse(out["execution_allowed"])
        self.assertGreaterEqual(out["cycles_executed"], 1)

    def test_tool_guard_blocks_unknown(self):
        g = AURALangChainToolGuard()
        r = g.run_tool("browser.navigate", {"url": "http://x"})
        self.assertEqual(r["status"], "BLOCKED")
        self.assertFalse(r["executed"])

    def test_tool_guard_sandbox(self):
        g = AURALangChainToolGuard()
        r = g.run_tool("math.calculate_stake", {"odds": 2.0})
        self.assertFalse(r["executed"])
        self.assertEqual(r["simulated_result"]["simulated_stake"], 0.0)

    def test_factory(self):
        chain = build_aura_langchain_chain(mode="ralph")
        # duck-typed invoke
        out = chain.invoke({"task_id": "t2", "snapshot": {"sources": ["x", "y"]}})
        self.assertFalse(out["execution_allowed"])

    def test_available_flag_is_bool(self):
        self.assertIsInstance(langchain_available(), bool)


if __name__ == "__main__":
    unittest.main()
