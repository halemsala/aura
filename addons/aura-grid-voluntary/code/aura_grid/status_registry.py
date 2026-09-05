"""In-memory + disk registry of worker telemetry for AURA Grid Manager."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StatusRegistry:
    def __init__(self, status_path: str | Path | None = None) -> None:
        import os
        self.path = Path(status_path or os.environ.get("AURA_GRID_STATUS_FILE", "grid_status.json"))
        self._lock = threading.RLock()
        self.workers: dict[str, dict[str, Any]] = {}
        self.master_meta: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_tasks": 0,
            "active_workers": 0,
            "verify_failures": 0,
        }

    def update_worker(self, worker_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            prev = self.workers.get(worker_id, {})
            prev.update(payload)
            prev["worker_id"] = worker_id
            prev["last_seen"] = datetime.now(timezone.utc).isoformat()
            prev["last_seen_unix"] = time.time()
            self.workers[worker_id] = prev
            self._flush_unlocked()

    def mark_offline(self, worker_id: str) -> None:
        with self._lock:
            if worker_id in self.workers:
                self.workers[worker_id]["online"] = False
                self.workers[worker_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
                self._flush_unlocked()

    def set_master(self, **kwargs: Any) -> None:
        with self._lock:
            self.master_meta.update(kwargs)
            self._flush_unlocked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        now = time.time()
        workers = []
        for w in self.workers.values():
            row = dict(w)
            age = now - float(row.get("last_seen_unix") or 0)
            row["stale_sec"] = round(age, 1)
            row["online"] = bool(row.get("online", True)) and age < 60
            workers.append(row)
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "master": dict(self.master_meta),
            "workers": workers,
            "worker_count": len(workers),
            "online_count": sum(1 for w in workers if w.get("online")),
        }

    def _flush_unlocked(self) -> None:
        data = self._snapshot_unlocked()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(self.path)


def format_status_table(snap: dict[str, Any]) -> str:
    lines = [
        f"AURA Grid Status  updated={snap.get('updated_at')}  online={snap.get('online_count')}/{snap.get('worker_count')}",
        f"Master completed={snap.get('master', {}).get('completed_tasks')}  active={snap.get('master', {}).get('active_workers')}",
        "-" * 100,
        f"{'WORKER':<22} {'ON':<3} {'CPU%':>5} {'GPU%':>5} {'TEMP':>5} {'PWR_W':>6} {'LIM_W':>6} {'RAM%':>5} {'CORES':>5}",
        "-" * 100,
    ]
    for w in snap.get("workers") or []:
        g = w.get("gpu") or {}
        lines.append(
            f"{str(w.get('worker_id', '')):<22} "
            f"{'Y' if w.get('online') else 'N':<3} "
            f"{float(w.get('cpu_pct') or 0):>5.0f} "
            f"{float(g.get('usage') or 0):>5.0f} "
            f"{float(g.get('temp') or 0):>5.0f} "
            f"{float(g.get('power_w') or 0):>6.0f} "
            f"{float(g.get('power_limit_w') or 0):>6.0f} "
            f"{float(w.get('ram_pct') or 0):>5.0f} "
            f"{int(w.get('cpu_cores') or 0):>5}"
        )
    if not snap.get("workers"):
        lines.append("(nenhum worker registrado)")
    return "\n".join(lines)
