from __future__ import annotations

import asyncio
import threading
import unittest

from engine.core.data_veracity import DataVeracityGate
from engine.core.feed_bus import FeedBusClient
from engine.core.observability import MetricsCollector


class V1277IntegrityObservabilityTests(unittest.TestCase):
    def test_veracity_rejects_regression_per_fixture(self):
        gate = DataVeracityGate()
        first = gate.sanitize({"fixture_id": "fx-1", "minute": 20, "corners_total": 4, "score": "1-0"})
        self.assertIsNotNone(first)
        self.assertIsNone(gate.sanitize({"fixture_id": "fx-1", "minute": 19, "corners_total": 3, "score": "1-0"}))
        other = gate.sanitize({"fixture_id": "fx-2", "minute": 1, "corners_total": 0, "score": "0-0"})
        self.assertIsNotNone(other)
        self.assertEqual(gate.snapshot()["rejected"], 1)

    def test_metrics_counter_snapshot_is_thread_safe(self):
        metrics = MetricsCollector()
        workers = [threading.Thread(target=lambda: [metrics.increment("signals") for _ in range(50)]) for _ in range(4)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(metrics.get_snapshot()["counters"]["signals"], 200)

    def test_feedbus_client_backoff_is_bounded_and_cancelable(self):
        client = FeedBusClient(max_retry_delay=2.0)
        stop = threading.Event()
        attempts = []

        async def connect(_uri):
            attempts.append(1)
            stop.set()
            raise RuntimeError("offline test")

        result = asyncio.run(client.connect_with_retry(connect, stop_event=stop))
        self.assertIsNone(result)
        self.assertEqual(len(attempts), 1)
        self.assertLessEqual(client._retry_delay, 2.0)


if __name__ == "__main__":
    unittest.main()
