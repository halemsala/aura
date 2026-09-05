import unittest
from aura_soup_bridge import build_plan, audit_plan, fingerprint


class SoupBridgeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "base": "Llama-3.1-8B-Instruct",
            "task": "sft",
            "data": {"max_length": 512},
            "training": {
                "stream_layers": True,
                "quantization": "4bit",
                "stream_source": "auto",
                "batch_size": 1,
                "lora": {"r": 16}
            }
        }

    def test_safe_plan(self):
        plan = build_plan(self.cfg)
        self.assertTrue(plan.stream_layers)
        self.assertEqual(plan.quantization, "4bit")
        self.assertFalse(plan.execution_allowed)
        self.assertTrue(plan.paper_trade)
        self.assertEqual(plan.status, "ADVISORY_ONLY")

    def test_audit_warns_for_beta_streaming(self):
        result = audit_plan(build_plan(self.cfg))
        self.assertTrue(any("beta" in w for w in result["warnings"]))
        self.assertFalse(result["execution_allowed"])

    def test_rejects_unknown_task(self):
        bad = dict(self.cfg)
        bad["task"] = "ppo"
        with self.assertRaises(ValueError):
            build_plan(bad)

    def test_fingerprint_is_deterministic(self):
        p = build_plan(self.cfg)
        self.assertEqual(fingerprint(p), fingerprint(p))


if __name__ == '__main__':
    unittest.main()
