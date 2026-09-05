from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.audit import AuditLogger
from aura_grid.pinning import cert_sha256_der
import hashlib

class AuditPinTests(unittest.TestCase):
    def test_audit_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.jsonl"
            log = AuditLogger(p, also_print=False)
            log.log("TEST_EVENT", x=1)
            log.close()
            line = p.read_text(encoding="utf-8").strip()
            obj = json.loads(line)
            self.assertEqual(obj["event"], "TEST_EVENT")
            self.assertEqual(obj["x"], 1)

    def test_der_hash(self):
        data = b"not-a-real-cert"
        self.assertEqual(cert_sha256_der(data), hashlib.sha256(data).hexdigest())

if __name__ == "__main__":
    unittest.main()
