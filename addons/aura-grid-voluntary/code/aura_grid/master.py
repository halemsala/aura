"""AURA Grid Master v6.0 — audit, spot verification, dynamic batch, poison-pill."""
from __future__ import annotations

import json
import os
import queue
import random
import signal
import socket
import threading
import time
from pathlib import Path
from typing import Any

from .audit import AuditLogger
from .codec import recv_msg, send_msg
from .ops import run_fixed_op
from .tls_util import server_context, tls_enabled
from .status_registry import StatusRegistry

MAX_RETRIES = int(os.environ.get("AURA_GRID_MAX_RETRIES", "3"))
TASKS_PER_CORE = int(os.environ.get("AURA_GRID_TASKS_PER_CORE", "5"))
VERIFICATION_RATE = float(os.environ.get("AURA_GRID_VERIFY_RATE", "0.1"))


def _task_key(item: dict[str, Any]) -> str:
    return json.dumps({"op": item.get("op"), "data": item.get("data"), "id": item.get("id")}, sort_keys=True, default=str)


class GridMaster:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5005,
        auth_token: str | None = None,
        results_path: str | Path | None = None,
        errors_path: str | Path | None = None,
        audit_path: str | Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token or os.environ.get("AURA_GRID_TOKEN", "")
        if not self.auth_token or self.auth_token == "SECURE_GRID_TOKEN_123":
            raise ValueError("Set a strong AURA_GRID_TOKEN.")
        if host in {"0.0.0.0", "::"} and os.environ.get("AURA_GRID_ALLOW_PUBLIC_BIND", "").lower() not in {
            "1", "true", "yes"
        }:
            raise ValueError("Refusing public bind without AURA_GRID_ALLOW_PUBLIC_BIND=true.")
        self.tasks_queue: queue.Queue = queue.Queue()
        self.failed_counts: dict[str, int] = {}
        self.completed_tasks = 0
        self.verify_failures = 0
        self._completed_lock = threading.Lock()
        self.active_workers = 0
        self._workers_lock = threading.Lock()
        self._live_conns: list[socket.socket] = []
        self._conns_lock = threading.Lock()
        self.running = True
        self.registry = StatusRegistry()
        self.sock_timeout = float(os.environ.get("AURA_GRID_SOCK_TIMEOUT", "30"))
        rp = Path(results_path or os.environ.get("AURA_GRID_RESULTS", "resultados.jsonl"))
        ep = Path(errors_path or os.environ.get("AURA_GRID_ERRORS", "erros.jsonl"))
        ap = Path(audit_path or os.environ.get("AURA_GRID_MASTER_AUDIT", "audit_master.jsonl"))
        for p in (rp, ep, ap):
            p.parent.mkdir(parents=True, exist_ok=True)
        self.results_path = rp
        self.errors_path = ep
        self.audit = AuditLogger(ap)
        self._file_lock = threading.Lock()
        self._out = open(rp, "a", encoding="utf-8")
        self._err = open(ep, "a", encoding="utf-8")

    def enqueue(self, data: Any, op: str = "sha256", task_id: Any = None) -> None:
        self.tasks_queue.put({"op": op, "data": data, "id": task_id})

    def _write_results(self, results: list[Any]) -> None:
        with self._file_lock:
            for res in results:
                self._out.write(json.dumps({"result": res}, ensure_ascii=False, default=str) + "\n")
            self._out.flush()

    def _write_error(self, payload: dict[str, Any]) -> None:
        with self._file_lock:
            self._err.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._err.flush()

    def _poison_or_requeue(self, batch: list[dict[str, Any]], reason: str, worker: str = "") -> None:
        for item in batch:
            key = _task_key(item)
            n = self.failed_counts.get(key, 0) + 1
            self.failed_counts[key] = n
            if n > MAX_RETRIES:
                self.audit.log("POISON_PILL", task_id=item.get("id"), attempts=n, reason=reason, worker=worker)
                self._write_error({"task": item, "error": "max_retries_exceeded", "reason": reason, "attempts": n})
            else:
                self.tasks_queue.put(item)

    def _verify_batch(self, batch: list[dict[str, Any]], results: list[Any], worker: str) -> list[Any]:
        """Spot-check VERIFICATION_RATE of results using fixed local ops."""
        accepted: list[Any] = []
        for i, res in enumerate(results):
            item = batch[i] if i < len(batch) else None
            if item is None:
                continue
            if random.random() < VERIFICATION_RATE:
                expected = run_fixed_op(str(item.get("op") or "sha256"), item.get("data"))
                # compare result payloads
                if expected.get("status") != "SUCCESS" or res.get("result") != expected.get("result"):
                    self.verify_failures += 1
                    self.audit.log(
                        "VERIFICATION_FAILED",
                        worker=worker,
                        task_id=item.get("id"),
                        expected=expected.get("result"),
                        got=res.get("result") if isinstance(res, dict) else res,
                    )
                    self._write_error({"task": item, "error": "verification_failed", "worker": worker})
                    continue
            accepted.append(res)
        return accepted

    def get_dynamic_batch(self, cpu_cores: int) -> list[dict[str, Any]] | None:
        size = max(5, max(1, int(cpu_cores)) * max(1, TASKS_PER_CORE))
        size = min(size, 256)
        batch: list[dict[str, Any]] = []
        while len(batch) < size:
            try:
                batch.append(self.tasks_queue.get_nowait())
            except queue.Empty:
                break
        return batch or None

    def handle_worker(self, conn: socket.socket, addr: Any) -> None:
        current_batch: list[dict[str, Any]] | None = None
        worker = f"{addr[0]}:{addr[1]}" if isinstance(addr, tuple) else str(addr)
        worker_cores = 4
        with self._conns_lock:
            self._live_conns.append(conn)
        try:
            conn.settimeout(self.sock_timeout)
            auth = recv_msg(conn)
            if not auth or auth.get("auth") != self.auth_token:
                self.audit.log("AUTH_FAILED", worker=worker)
                return
            worker_cores = int(auth.get("cpu_cores") or auth.get("max_workers") or 4)
            self.audit.log("WORKER_CONNECTED", worker=worker, cores=worker_cores, version=auth.get("version"))
            tel = auth.get("telemetry") or {}
            self.registry.update_worker(worker, {
                "online": True,
                "cpu_cores": worker_cores,
                "version": auth.get("version"),
                "cpu_pct": tel.get("cpu_pct"),
                "ram_pct": tel.get("ram_pct"),
                "gpu": tel.get("gpu") or {},
            })
            self.registry.set_master(active_workers=self.active_workers + 1)
            with self._workers_lock:
                self.active_workers += 1
            while self.running:
                if current_batch is None and self.tasks_queue.empty():
                    send_msg(conn, {"task": "WAIT"})
                    idle = recv_msg(conn)
                    if idle is None:
                        break
                    if isinstance(idle, dict) and idle.get("telemetry"):
                        tel = idle["telemetry"]
                        self.registry.update_worker(worker, {
                            "online": True,
                            "cpu_pct": tel.get("cpu_pct"),
                            "ram_pct": tel.get("ram_pct"),
                            "cpu_cores": worker_cores,
                            "gpu": tel.get("gpu") or {},
                        })
                    time.sleep(0.3)
                    continue
                if current_batch is None:
                    current_batch = self.get_dynamic_batch(worker_cores)
                    if not current_batch:
                        continue
                send_msg(conn, {"task": "BATCH_PROCESS", "data": current_batch})
                resp = recv_msg(conn)
                if resp is None:
                    self.audit.log("WORKER_DIED", worker=worker, reason="null_response")
                    self._poison_or_requeue(current_batch, "disconnect", worker)
                    current_batch = None
                    break
                st = resp.get("status")
                if st == "BATCH_SUCCESS":
                    results = resp.get("results") or []
                    accepted = self._verify_batch(current_batch, results, worker)
                    self._write_results(accepted)
                    with self._completed_lock:
                        self.completed_tasks += len(accepted)
                    self.audit.log("BATCH_SUCCESS", worker=worker, size=len(accepted), completed=self.completed_tasks)
                    self.registry.set_master(completed_tasks=self.completed_tasks, active_workers=self.active_workers, verify_failures=self.verify_failures)
                    current_batch = None
                elif st == "SUCCESS":
                    accepted = self._verify_batch(current_batch[:1], [resp], worker)
                    self._write_results(accepted)
                    with self._completed_lock:
                        self.completed_tasks += len(accepted)
                    current_batch = None
                elif st == "PAUSED_FOR_USER":
                    time.sleep(3)
                elif st == "BLOCKED":
                    self._poison_or_requeue(current_batch, "blocked", worker)
                    current_batch = None
                else:
                    self._poison_or_requeue(current_batch, f"status:{st}", worker)
                    current_batch = None
                    break
        except socket.timeout:
            self.audit.log("TIMEOUT", worker=worker)
            if current_batch:
                self._poison_or_requeue(current_batch, "timeout", worker)
        except Exception as e:
            self.audit.log("WORKER_ERROR", worker=worker, error=str(e))
            if current_batch:
                self._poison_or_requeue(current_batch, str(e), worker)
        finally:
            with self._workers_lock:
                self.active_workers = max(0, self.active_workers - 1)
            self.registry.mark_offline(worker)
            self.registry.set_master(active_workers=self.active_workers)
            with self._conns_lock:
                if conn in self._live_conns:
                    self._live_conns.remove(conn)
            try:
                conn.close()
            except Exception:
                pass

    def broadcast_shutdown(self) -> None:
        with self._conns_lock:
            conns = list(self._live_conns)
        for c in conns:
            try:
                send_msg(c, {"task": "SHUTDOWN"})
            except Exception:
                pass

    def request_shutdown(self) -> None:
        self.running = False
        self.broadcast_shutdown()
        try:
            with socket.create_connection(
                (self.host if self.host not in {"0.0.0.0", "::"} else "127.0.0.1", self.port), timeout=1
            ):
                pass
        except Exception:
            pass

    def start_server(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(16)
            self.audit.log("SERVER_START", host=self.host, port=self.port, tls=tls_enabled(), verify_rate=VERIFICATION_RATE)
            if tls_enabled():
                cert = os.environ.get("AURA_GRID_TLS_CERT", "cert.pem")
                key = os.environ.get("AURA_GRID_TLS_KEY", "key.pem")
                ctx = server_context(cert, key)
                accept_sock = ctx.wrap_socket(s, server_side=True)
            else:
                accept_sock = s
            while self.running:
                try:
                    accept_sock.settimeout(1.0)
                    try:
                        conn, addr = accept_sock.accept()
                    except socket.timeout:
                        continue
                    threading.Thread(target=self.handle_worker, args=(conn, addr), daemon=True).start()
                except Exception as e:
                    if self.running:
                        self.audit.log("ACCEPT_ERROR", error=str(e))
            self.broadcast_shutdown()
            if tls_enabled() and accept_sock is not s:
                try:
                    accept_sock.close()
                except Exception:
                    pass

    def close(self) -> None:
        self.audit.log("SYSTEM_STOPPED", completed=self.completed_tasks, verify_failures=self.verify_failures)
        self.audit.close()
        with self._file_lock:
            for fp in (self._out, self._err):
                try:
                    fp.flush()
                    fp.close()
                except Exception:
                    pass


def main() -> None:
    host = os.environ.get("AURA_GRID_BIND", "127.0.0.1")
    port = int(os.environ.get("AURA_GRID_MASTER_PORT", "5005"))
    master = GridMaster(host=host, port=port)
    n = int(os.environ.get("AURA_GRID_DEMO_TASKS", "20"))
    for i in range(n):
        master.enqueue({"payload": f"sample_{i}"}, op="sha256", task_id=i)

    def _sig(_s, _f):
        master.request_shutdown()

    signal.signal(signal.SIGINT, _sig)
    try:
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass

    threading.Thread(target=master.start_server, daemon=True).start()
    while master.running and master.completed_tasks < n:
        print(f"Done={master.completed_tasks}/{n} workers={master.active_workers} vfail={master.verify_failures}")
        if master.tasks_queue.empty() and master.active_workers == 0 and master.completed_tasks < n:
            # wait for workers
            time.sleep(2)
            if master.tasks_queue.empty() and master.active_workers == 0:
                break
        time.sleep(2)
        if master.completed_tasks >= n:
            break
    master.request_shutdown()
    time.sleep(0.5)
    master.close()


if __name__ == "__main__":
    main()
