from __future__ import annotations
"""Ring buffer para feed — uso opcional junto ao bridge existente."""
import json
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

logger = logging.getLogger("aura.feed_buffer")


class SyncFeedBuffer:
    """Versao thread-safe (bridge atual e ThreadingHTTPServer)."""

    def __init__(self, flush_interval: float = 0.5, max_batch: int = 500, data_dir: Optional[str] = None):
        self._buffer: Deque[dict] = deque()
        self._lock = threading.Lock()
        self._flush_interval = flush_interval
        self._max_batch = max_batch
        base = Path(data_dir or "bridge/data")
        base.mkdir(parents=True, exist_ok=True)
        self.feed_file = base / "feed.jsonl"
        self.latest_file = base / "latest.json"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="FeedBufferFlush")
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._thread.start()
        self._started = True

    def append(self, record: dict) -> None:
        with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self._max_batch:
                batch = list(self._buffer)
                self._buffer.clear()
            else:
                batch = None
        if batch:
            self._sync_flush(batch)

    def _loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self._flush_interval)
            with self._lock:
                if not self._buffer:
                    continue
                batch = list(self._buffer)
                self._buffer.clear()
            self._sync_flush(batch)

    def _sync_flush(self, batch: List[dict]) -> None:
        if not batch:
            return
        try:
            with open(self.feed_file, "a", encoding="utf-8") as f:
                for record in batch:
                    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            latest = batch[-1]
            self.latest_file.write_text(json.dumps(latest, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception as e:
            logger.error("feed flush fail: %s", e)


feed_buffer = SyncFeedBuffer()
