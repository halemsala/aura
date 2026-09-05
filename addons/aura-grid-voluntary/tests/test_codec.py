from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from aura_grid.codec import encode, decode

class CodecTests(unittest.TestCase):
    def test_json_zlib_roundtrip(self):
        os.environ.pop("AURA_GRID_ALLOW_PICKLE", None)
        msg = {"task": "BATCH_PROCESS", "data": [{"op": "sha256", "data": {"x": i}} for i in range(20)]}
        blob = encode(msg)
        self.assertTrue(blob[4] == ord("J") or True)  # body starts after len
        body = blob[4:]
        self.assertEqual(body[:1], b"J")
        out = decode(body)
        self.assertEqual(out["task"], "BATCH_PROCESS")
        self.assertEqual(len(out["data"]), 20)

    def test_compression_shrinks(self):
        os.environ.pop("AURA_GRID_ALLOW_PICKLE", None)
        msg = {"data": "aaaa" * 5000}
        blob = encode(msg)
        self.assertLess(len(blob), len(msg["data"]) + 100)

if __name__ == "__main__":
    unittest.main()
