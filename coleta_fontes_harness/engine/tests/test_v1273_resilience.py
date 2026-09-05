from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from engine.core.semantic_cache import LLMSemanticCache
from engine.data_store import SQLiteBatchWriter, init_schema


class V1273ResilienceTests(unittest.TestCase):
    def test_semantic_cache_reuses_only_same_critical_state(self):
        cache = LLMSemanticCache(ttl=0.2, maxsize=4)
        features = {
            "fixture_id": "fixture-1",
            "minute": 30,
            "score": [0, 0],
            "corners_total": 5,
            "wom_trend": -2.4,
            "route": "advisory",
            "query": "analise",
        }
        cache.set_features(features, "HOLD")
        self.assertEqual(cache.get_features(features), "HOLD")
        changed = dict(features, minute=31)
        self.assertIsNone(cache.get_features(changed))
        time.sleep(0.21)
        self.assertIsNone(cache.get_features(features))

    def test_batch_writer_flushes_grouped_rows(self):
        with tempfile.TemporaryDirectory(prefix="aura_v1273_db_") as td:
            db_path = str(Path(td) / "test.sqlite")
            init_schema(db_path)
            writer = SQLiteBatchWriter(db_path, interval_sec=10, max_queue=16)
            sql = "INSERT INTO model_versions (model_version, model_name, schema_version, checksum, metrics_json, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            rows = [
                ("v1273-a", "test", "1", "a", "{}", "batch", 1.0),
                ("v1273-b", "test", "1", "b", "{}", "batch", 2.0),
            ]
            for row in rows:
                self.assertTrue(writer.enqueue(sql, row))
            self.assertEqual(writer.flush(), 2)
            writer.close()
            import sqlite3
            conn = sqlite3.connect(db_path)
            try:
                count = conn.execute("SELECT COUNT(*) FROM model_versions WHERE model_version LIKE 'v1273-%'").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
