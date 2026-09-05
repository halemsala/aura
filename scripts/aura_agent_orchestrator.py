#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Agent Orchestrator v1.0
Scheduler inteligente de agentes com priorização dinâmica, load balancing e circuit breaker.
"""
import os, sys, json, time, threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass, asdict
import heapq

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)


@dataclass
class AgentTask:
    agent_id: str
    priority: int  # 1 = crítico, 10 = baixo
    function: str
    payload: dict
    created_at: float
    max_retries: int = 3
    timeout_seconds: int = 30

    def __lt__(self, other):
        return self.priority < other.priority


class CircuitBreaker:
    """Circuit breaker para evitar cascata de falhas."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure = 0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.RLock()

    def can_execute(self) -> bool:
        with self._lock:
            if self._state == "CLOSED":
                return True
            if self._state == "OPEN":
                if time.time() - self._last_failure > self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    return True
                return False
            return True  # HALF_OPEN

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._state = "CLOSED"

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure = time.time()
            if self._failures >= self.failure_threshold:
                self._state = "OPEN"

    def state(self) -> str:
        with self._lock:
            return self._state


class AgentOrchestrator:
    """Orquestrador inteligente de agentes AURA."""

    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self._queue = []
        self._running = {}
        self._breakers = {}
        self._stats = {"submitted": 0, "completed": 0, "failed": 0, "retried": 0}
        self._lock = threading.RLock()
        self._executor = threading.Thread(target=self._process_loop, daemon=True)
        self._executor.start()

    def submit(self, task: AgentTask) -> str:
        with self._lock:
            task_id = f"{task.agent_id}_{task.function}_{int(time.time()*1000)}"
            heapq.heappush(self._queue, task)
            self._stats["submitted"] += 1
            return task_id

    def _get_breaker(self, agent_id: str) -> CircuitBreaker:
        if agent_id not in self._breakers:
            self._breakers[agent_id] = CircuitBreaker()
        return self._breakers[agent_id]

    def _process_loop(self):
        while True:
            time.sleep(0.1)
            with self._lock:
                if not self._queue or len(self._running) >= self.max_concurrent:
                    continue

                task = heapq.heappop(self._queue)
                breaker = self._get_breaker(task.agent_id)

                if not breaker.can_execute():
                    print(f"[ORCH] Circuit breaker OPEN para {task.agent_id}, reenfileirando")
                    heapq.heappush(self._queue, task)
                    continue

                thread = threading.Thread(target=self._execute_task, args=(task, breaker))
                self._running[task.agent_id] = thread
                thread.start()

    def _execute_task(self, task: AgentTask, breaker: CircuitBreaker):
        try:
            print(f"[ORCH] Executando {task.agent_id}.{task.function} (prioridade {task.priority})")

            # Simular execução (substituir por chamada real ao agente)
            result = self._call_agent(task)

            if result.get("success"):
                breaker.record_success()
                self._stats["completed"] += 1
            else:
                raise Exception(result.get("error", "unknown"))

        except Exception as e:
            print(f"[ORCH] Falha em {task.agent_id}: {e}")
            breaker.record_failure()

            if task.max_retries > 0:
                task.max_retries -= 1
                task.priority += 1  # Diminuir prioridade no retry
                with self._lock:
                    heapq.heappush(self._queue, task)
                    self._stats["retried"] += 1
            else:
                self._stats["failed"] += 1
        finally:
            with self._lock:
                self._running.pop(task.agent_id, None)

    def _call_agent(self, task: AgentTask) -> dict:
        """Chamada real ao agente. Substituir pela integração com engine."""
        import random
        time.sleep(0.5)  # Simular latência
        if random.random() > 0.9:  # 10% chance de falha simulada
            return {"success": False, "error": "simulated_failure"}
        return {"success": True, "data": {"agent": task.agent_id, "function": task.function}}

    def stats(self) -> dict:
        with self._lock:
            return {
                **self._stats,
                "queue_size": len(self._queue),
                "running": len(self._running),
                "circuit_breakers": {k: v.state() for k, v in self._breakers.items()}
            }

    def export_stats(self):
        path = LOGDIR / "orchestrator_stats.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.stats(), f, indent=2, ensure_ascii=False)


def schedule_priority_analysis(fixture_data: dict) -> List[AgentTask]:
    """Gera tasks prioritárias baseadas na análise da partida."""
    tasks = []

    # Prioridade 1: Análise de escanteios (sempre crítico)
    tasks.append(AgentTask(
        agent_id="corner_intelligence",
        priority=1,
        function="analyze_corners",
        payload={"fixture": fixture_data},
        created_at=time.time(),
        timeout_seconds=10
    ))

    # Prioridade 2: Modelo Hawkes
    tasks.append(AgentTask(
        agent_id="hawkes_corners",
        priority=2,
        function="build_hawkes_from_payload",
        payload={"fixture": fixture_data},
        created_at=time.time(),
        timeout_seconds=15
    ))

    # Prioridade 3: Edge de mercado
    tasks.append(AgentTask(
        agent_id="market_edge",
        priority=3,
        function="analyze_market",
        payload={"fixture": fixture_data},
        created_at=time.time(),
        timeout_seconds=20
    ))

    # Prioridade 5: Diagnóstico (não crítico)
    tasks.append(AgentTask(
        agent_id="system_medic",
        priority=5,
        function="diagnose",
        payload={},
        created_at=time.time(),
        timeout_seconds=30
    ))

    return tasks


def main():
    print("=" * 60)
    print("AURA Agent Orchestrator v1.0")
    print("=" * 60)

    orch = AgentOrchestrator(max_concurrent=3)

    # Simular fixture
    fixture = {"id": "test_123", "home": "Time A", "away": "Time B", "minute": 45}
    tasks = schedule_priority_analysis(fixture)

    for task in tasks:
        orch.submit(task)

    time.sleep(5)
    orch.export_stats()

    print("\nEstatísticas:")
    print(json.dumps(orch.stats(), indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
