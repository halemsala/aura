#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Orchestrator — jobs + checkpoint + circuit breaker (stdlib asyncio)."""
from __future__ import annotations
import argparse, asyncio, json, os, sqlite3, time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"

@dataclass
class Job:
    id: str
    agent: str
    task: str
    status: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3

class HermesOrchestrator:
    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
        self.db_path = self.root / "orchestrator" / "state_checkpoints" / "checkpoints.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.agents: Dict[str, Callable] = {}
        self.circuit_failures: Dict[str, int] = {}
        self.circuit_threshold = 5
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path), timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, agent TEXT, task TEXT, status TEXT,
                created_at REAL, started_at REAL, finished_at REAL,
                result TEXT, retry_count INTEGER, max_retries INTEGER)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS checkpoints (
                job_id TEXT, ts REAL, state TEXT)""")
            conn.commit()

    def register_agent(self, name: str, handler: Callable) -> None:
        self.agents[name] = handler

    def _circuit_open(self, agent: str) -> bool:
        return self.circuit_failures.get(agent, 0) >= self.circuit_threshold

    def _persist(self, job: Job) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job.id, job.agent, job.task, job.status, job.created_at,
                 job.started_at, job.finished_at,
                 json.dumps(job.result) if job.result is not None else None,
                 job.retry_count, job.max_retries),
            )
            conn.commit()

    def _checkpoint(self, job: Job) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO checkpoints (job_id, ts, state) VALUES (?,?,?)",
                (job.id, time.time(), json.dumps(asdict(job), default=str)),
            )
            conn.commit()

    async def submit(self, agent: str, task: str, payload: Optional[dict] = None) -> Job:
        job = Job(
            id=f"job_{int(time.time()*1000)}",
            agent=agent, task=task, status=JobStatus.PENDING.value,
            created_at=time.time(),
        )
        self._persist(job)
        asyncio.create_task(self._run(job, payload or {}))
        return job

    async def _run(self, job: Job, payload: dict) -> None:
        if self._circuit_open(job.agent):
            job.status = JobStatus.ESCALATED.value
            job.finished_at = time.time()
            job.result = {"error": "circuit_open"}
            self._persist(job)
            return
        handler = self.agents.get(job.agent)
        if not handler:
            job.status = JobStatus.FAILED.value
            job.result = {"error": f"unknown agent {job.agent}"}
            job.finished_at = time.time()
            self._persist(job)
            return
        job.status = JobStatus.RUNNING.value
        job.started_at = time.time()
        self._persist(job)
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(payload)
            else:
                result = handler(payload)
            job.status = JobStatus.SUCCESS.value
            job.result = result if isinstance(result, dict) else {"result": result}
            self.circuit_failures[job.agent] = 0
        except Exception as e:
            self.circuit_failures[job.agent] = self.circuit_failures.get(job.agent, 0) + 1
            job.retry_count += 1
            if job.retry_count <= job.max_retries:
                job.status = JobStatus.PENDING.value
                self._persist(job)
                await asyncio.sleep(min(2 ** job.retry_count, 30))
                await self._run(job, payload)
                return
            job.status = JobStatus.FAILED.value
            job.result = {"error": str(e), "retries": job.retry_count}
        job.finished_at = time.time()
        self._persist(job)
        self._checkpoint(job)

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "agent": row[1], "task": row[2], "status": row[3],
            "created_at": row[4], "started_at": row[5], "finished_at": row[6],
            "result": json.loads(row[7]) if row[7] else None,
            "retry_count": row[8], "max_retries": row[9],
        }

async def _demo(root: str) -> None:
    orch = HermesOrchestrator(root)
    async def diagnostic(_):
        await asyncio.sleep(0.2)
        return {"health_score": 95, "paper_trade": True}
    orch.register_agent("diagnostic", diagnostic)
    j = await orch.submit("diagnostic", "full_scan")
    await asyncio.sleep(1)
    print(json.dumps(orch.get_job(j.id), indent=2))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "."))
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if args.once:
        asyncio.run(_demo(args.root))
    else:
        print("Use --once")
