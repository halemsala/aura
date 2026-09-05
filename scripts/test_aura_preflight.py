"""Tests for the read-only AURA Windows distribution preflight."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aura_preflight import REQUIRED_FILES, run


class PreflightTests(unittest.TestCase):
    def _make_root(self, directory: Path) -> Path:
        root = directory / "aura"
        for relative in REQUIRED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() == ".bat":
                path.write_bytes(b"@echo off\r\n")
            elif path.name == "config.yaml":
                path.write_text("voice: pt-BR-AntonioNeural\nxtts_enabled: false\n", encoding="utf-8")
            elif path.name == "PACKAGE_RELEASE.txt":
                path.write_text("AURA-TEST-RELEASE\n", encoding="utf-8")
            else:
                path.write_text("PAPER TRADE ONLY; real orders are disabled.\n", encoding="utf-8")
        return root

    def test_paper_trade_guard_passes_without_live_execution_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("aura_preflight.port_open", return_value=False):
                checks, rc = run(self._make_root(Path(directory)))
            paper = next(check for check in checks if check["name"] == "paper_trade_guard")
            self.assertEqual(rc, 0)
            self.assertTrue(paper["ok"])

    def test_paper_trade_guard_blocks_explicit_live_order_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_root(Path(directory))
            (root / "engine").mkdir(parents=True, exist_ok=True)
            (root / "engine/server.py").write_text("PAPER TRADE ONLY\nexecute a real order\n", encoding="utf-8")
            with patch("aura_preflight.port_open", return_value=False):
                checks, rc = run(root)
            paper = next(check for check in checks if check["name"] == "paper_trade_guard")
            self.assertEqual(rc, 1)
            self.assertFalse(paper["ok"])


if __name__ == "__main__":
    unittest.main()
