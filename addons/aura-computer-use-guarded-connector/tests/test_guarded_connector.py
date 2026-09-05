"""Testes offline — comprovam bloqueio padrão (sem mouse/rede/driver)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from connector import GuardedComputerUseConnector  # noqa: E402
from policy import GuardedPolicy, load_manifest  # noqa: E402


class ManifestTests(unittest.TestCase):
    def test_manifest_policies(self):
        m = load_manifest(ROOT / "config" / "manifest.json")
        p = m["policies"]
        self.assertFalse(p["computer_use_enabled"])
        self.assertFalse(p["execution_allowed"])
        self.assertTrue(p["approval_required"])
        self.assertFalse(p["network_allowed"])
        self.assertFalse(p["authenticated_profiles_allowed"])
        self.assertFalse(p["scheduler_enabled"])
        self.assertFalse(m["driver_external_installed"])
        self.assertEqual(m["services_started"], [])


class PolicyTests(unittest.TestCase):
    def test_assert_inert(self):
        pol = GuardedPolicy.from_manifest(load_manifest(ROOT / "config" / "manifest.json"))
        pol.assert_inert()

    def test_rejects_enabled_cu(self):
        pol = GuardedPolicy(computer_use_enabled=True)
        with self.assertRaises(RuntimeError):
            pol.assert_inert()


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.c = GuardedComputerUseConnector(
            GuardedPolicy.from_manifest(load_manifest(ROOT / "config" / "manifest.json"))
        )

    def test_status_inert(self):
        s = self.c.status()
        self.assertFalse(s["computer_use_enabled"])
        self.assertFalse(s["execution_allowed"])
        self.assertTrue(s["approval_required"])
        self.assertFalse(s["network_allowed"])
        self.assertFalse(s["driver_external_installed"])
        self.assertEqual(s["services_started"], [])

    def test_action_blocked(self):
        r = self.c.request_action("click", "button")
        self.assertTrue(r.blocked)
        self.assertFalse(r.executed)
        self.assertIn("computer_use_disabled", r.reason)

    def test_sensitive_blocked(self):
        r = self.c.request_action("open", "user email inbox")
        self.assertTrue(r.blocked)
        self.assertFalse(r.executed)
        self.assertIn("blocked_sensitive", r.reason)

    def test_yolo_token_blocked(self):
        r = self.c.request_action("run", "yolo unrestricted")
        self.assertTrue(r.blocked)
        self.assertFalse(r.executed)


if __name__ == "__main__":
    unittest.main()
