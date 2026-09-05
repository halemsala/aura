from __future__ import annotations
import queue, sqlite3, threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class WriteJob:
    sql: str
    params: tuple

class DatabaseRuntime:
    def __init__(self, path: str, *, queue_size: int = 8192, batch_size: int = 64) -> None:
        self.path = str(Path(path))
        self.batch_size = batch_size
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._writer_loop, name="sqlite-single-writer", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._initialize_schema_once()
        self._thread.start()
        self._started = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize_schema_once(self) -> None:
        conn = self._connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
            conn.commit()
        finally:
            conn.close()

    def submit(self, sql: str, params: tuple = ()) -> None:
        self._queue.put_nowait(WriteJob(sql, params))

    def _writer_loop(self) -> None:
        conn = self._connect()
        try:
            while not self._stop.is_set():
                try:
                    first = self._queue.get(timeout=0.250)
                except queue.Empty:
                    continue
                if first is None:
                    break
                batch = [first]
                while len(batch) < self.batch_size:
                    try:
                        job = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if job is None:
                        self._stop.set()
                        break
                    batch.append(job)
                try:
                    conn.execute("BEGIN")
                    for job in batch:
                        conn.execute(job.sql, job.params)
                    conn.commit()
                except Exception:
                    conn.rollback()
        finally:
            conn.close()

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._started:
            self._thread.join(timeout=5)
