import unittest

from aura_maximizer import status
from aura_maximizer.agents import run_advisory
from aura_maximizer.connectors import ReadOnlyConnectorCatalog
from aura_maximizer.contracts import ConnectorRequest
from aura_maximizer.firewall import parse_llm_output
from aura_maximizer.routines import build_default_routines


class AddonSafetyTests(unittest.TestCase):
    def test_status_is_inert(self):
        s = status()
        self.assertTrue(s["paper_trade"])
        self.assertFalse(s["execution_allowed"])
        self.assertFalse(s["network_enabled"])
        self.assertFalse(s["scheduler_enabled"])
        self.assertFalse(s["tool_execution_enabled"])

    def test_firewall_rejects_invalid_and_extra_fields(self):
        self.assertEqual(parse_llm_output("not json").decision, "BLOCK")
        self.assertEqual(parse_llm_output({"decision": "ADVISORY", "rationale": "ok", "confidence": 0.5, "exec": True}).decision, "BLOCK")
        self.assertEqual(parse_llm_output({"decision": "ADVISORY", "rationale": "ok", "confidence": 2}).decision, "BLOCK")

    def test_firewall_accepts_closed_advisory(self):
        result = parse_llm_output({"decision": "AGUARDA", "rationale": "evidência insuficiente", "confidence": 0.4})
        self.assertEqual(result.decision, "AGUARDA")
        self.assertTrue(result.paper_trade)
        self.assertFalse(result.execution_allowed)

    def test_connector_is_read_only_and_no_secret(self):
        catalog = ReadOnlyConnectorCatalog()
        plan = catalog.plan(ConnectorRequest("documents", "search", {"query": "procedimento"}))
        self.assertEqual(plan["status"], "PLANNED")
        with self.assertRaises(PermissionError):
            catalog.plan(ConnectorRequest("documents", "delete"))
        with self.assertRaises(PermissionError):
            catalog.plan(ConnectorRequest("documents", "search", {"token": "secret"}))

    def test_routines_are_disabled(self):
        self.assertTrue(build_default_routines())
        self.assertTrue(all(not r.enabled for r in build_default_routines()))

    def test_agents_are_advisory(self):
        result = run_advisory({"fixture_id": "x", "minute": 35, "sources": ["source-1"], "data_quality": "VALID"})
        self.assertFalse(result.tool_calls)
        self.assertFalse(result.decision.execution_allowed)


if __name__ == "__main__":
    unittest.main()
