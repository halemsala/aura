import unittest
from aura_maximizer.orchestrator import (
    AURAHermesPipeline, AURAProposal, Evidence, HermesReview, Decision
)


def aura_ok(snapshot):
    return AURAProposal('t-1', 'análise', ('achado',), (Evidence('fixture', snapshot, 'fresh', 0.9),), 'aguardar')


def hermes_ok(proposal):
    return HermesReview(proposal.task_id, True, (), (), 0.91, Decision.ADVISORY)


class FullPipelineTests(unittest.TestCase):
    def test_cooperation_is_advisory(self):
        result = AURAHermesPipeline().run('t-1', {'x': 1}, aura_ok, hermes_ok)
        self.assertEqual(result.decision, Decision.ADVISORY)
        self.assertFalse(result.execution_allowed)
        self.assertTrue(result.audit_hash)

    def test_missing_evidence_blocks_to_aguarda(self):
        def weak(snapshot):
            return AURAProposal('t-1', 'análise', ('achado',), (), None)
        result = AURAHermesPipeline().run('t-1', {'x': 1}, weak, hermes_ok)
        self.assertEqual(result.decision, Decision.AGUARDA)
        self.assertFalse(result.execution_allowed)

    def test_hermes_can_block(self):
        def hermes_block(proposal):
            return HermesReview(proposal.task_id, False, ('risco',), ('fonte',), 0.2, Decision.BLOCK)
        result = AURAHermesPipeline().run('t-1', {'x': 1}, aura_ok, hermes_block)
        self.assertEqual(result.decision, Decision.BLOCK)
        self.assertFalse(result.execution_allowed)

    def test_cycle_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            AURAHermesPipeline(max_cycles=4)


if __name__ == '__main__':
    unittest.main()
