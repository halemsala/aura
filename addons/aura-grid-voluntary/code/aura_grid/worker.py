"""AURA Grid Worker v6.0 — cert pin, audit JSONL, batch multicore."""
from __future__ import annotations

import concurrent.futures
import os
import signal
import socket
import time
import threading
from typing import Any

from .audit import AuditLogger
from .codec import recv_msg, send_msg
from .ops import run_fixed_op
from .pinning import expected_pin, verify_peer_pin
from .pool_ops import process_batch_item
from .tls_util import client_context, tls_enabled
from .gpu_sensors import read_gpu0, read_host_snapshot

DEFAULT_MAX_CPU = 85.0
DEFAULT_MAX_GPU = 30.0


def set_low_priority() -> str:
    try:
        import psutil
        p = psutil.Process(os.getpid())
        if os.name == "nt":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            return "windows_BELOW_NORMAL"
        p.nice(10)
        return f"unix_nice_{p.nice()}"
    except Exception as e:
        return f"priority_unchanged:{e}"


class SystemMonitor:
    """Pause donation on user load OR unsafe GPU temperatures (not utilization alone).

    Modern GPUs are designed for high utilization; silicon life is driven by
    temperature and voltage. Thresholds are env-overridable.
    """

    def __init__(
        self,
        max_cpu: float | None = None,
        max_gpu: float | None = None,
    ) -> None:
        import os
        self.max_cpu = float(os.environ.get("AURA_GRID_MAX_CPU_PCT", max_cpu if max_cpu is not None else DEFAULT_MAX_CPU))
        # High util is OK if cool; util limit is soft / secondary
        self.max_gpu = float(os.environ.get("AURA_GRID_MAX_GPU_PCT", max_gpu if max_gpu is not None else 95.0))
        self.max_gpu_temp_c = float(os.environ.get("AURA_GRID_MAX_GPU_TEMP_C", "75"))
        self.max_gpu_mem_temp_c = float(os.environ.get("AURA_GRID_MAX_GPU_MEM_TEMP_C", "85"))
        self.max_hotspot_c = float(os.environ.get("AURA_GRID_MAX_HOTSPOT_C", "95"))
        self.is_busy = False
        self.running = True
        self.ignore_cpu = os.environ.get("AURA_GRID_IGNORE_SELF_CPU", "").lower() in {"1", "true", "yes"}
        self.last_metrics: dict = {}

    def _read_gpu(self) -> dict:
        return read_gpu0()

    def check_resources(self) -> None:
        try:
            import psutil
            psutil.cpu_percent(interval=None)
        except ImportError:
            import os, time
            while self.running:
                self.is_busy = os.environ.get("AURA_GRID_FORCE_BUSY", "").lower() in {"1", "true"}
                time.sleep(2)
            return
        import psutil
        import time
        while self.running:
            cpu = float(psutil.cpu_percent(interval=2))
            g = self._read_gpu()
            self.last_metrics = {"cpu": cpu, **g}
            thermal = False
            if g["ok"]:
                if g["temp"] > self.max_gpu_temp_c:
                    thermal = True
                if g["mem_temp"] > 0 and g["mem_temp"] > self.max_gpu_mem_temp_c:
                    thermal = True
                if g["hotspot"] > 0 and g["hotspot"] > self.max_hotspot_c:
                    thermal = True
            busy_util = (g["usage"] > self.max_gpu) if g["ok"] else False
            busy_cpu = (not self.ignore_cpu) and (cpu > self.max_cpu)
            busy = thermal or busy_util or busy_cpu
            if busy and not self.is_busy:
                reason = "THERMAL" if thermal else "UTIL"
                print(
                    f"[PAUSE {reason}] CPU={cpu:.0f}% GPU={g['usage']:.0f}% "
                    f"Temp={g['temp']:.0f}C Mem={g['mem_temp']:.0f}C Hot={g['hotspot']:.0f}C"
                )
            if not busy and self.is_busy:
                print(f"[RESUME] Temp={g['temp']:.0f}C GPU={g['usage']:.0f}%")
            self.is_busy = busy



class GridWorker:
    def __init__(
        self,
        master_host: str,
        master_port: int = 5005,
        auth_token: str | None = None,
        max_workers: int | None = None,
        audit_path: str | None = None,
    ) -> None:
        self.master_host = master_host
        self.master_port = master_port
        self.auth_token = auth_token or os.environ.get("AURA_GRID_TOKEN", "")
        if not self.auth_token or self.auth_token == "SECURE_GRID_TOKEN_123":
            raise ValueError("Set a strong AURA_GRID_TOKEN.")
        self.monitor = SystemMonitor()
        self.cpu_cores = os.cpu_count() or 1
        env_w = os.environ.get("AURA_GRID_MAX_WORKERS")
        self.max_workers = max(
            1,
            min(int(env_w) if env_w else (max_workers or max(1, self.cpu_cores // 2)), self.cpu_cores),
        )
        self.pool = concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
        self.sock_timeout = float(os.environ.get("AURA_GRID_SOCK_TIMEOUT", "30"))
        self.shutdown_flag = False
        self.audit = AuditLogger(audit_path or os.environ.get("AURA_GRID_WORKER_AUDIT", "audit_worker.jsonl"))
        self.require_pin = os.environ.get("AURA_GRID_REQUIRE_CERT_PIN", "").lower() in {"1", "true", "yes"}

    def request_shutdown(self) -> None:
        self.shutdown_flag = True
        self.monitor.running = False

    def _connect(self):
        raw = socket.create_connection((self.master_host, self.master_port), timeout=self.sock_timeout)
        if tls_enabled():
            return client_context().wrap_socket(raw, server_hostname=self.master_host)
        return raw

    def start(self) -> None:
        threading.Thread(target=self.monitor.check_resources, daemon=True).start()
        self.audit.log("SYSTEM_START", version="6.0", cores=self.cpu_cores, max_workers=self.max_workers)
        while not self.shutdown_flag:
            try:
                if self.monitor.is_busy:
                    time.sleep(5)
                    continue
                with self._connect() as s:
                    s.settimeout(self.sock_timeout)
                    if tls_enabled():
                        ok, actual = verify_peer_pin(s)
                        pin = expected_pin()
                        if pin and not ok:
                            self.audit.log("SECURITY_ALERT", reason="cert_pin_mismatch", received=actual, expected=pin)
                            time.sleep(10)
                            continue
                        if self.require_pin and not pin:
                            self.audit.log("SECURITY_ALERT", reason="pin_required_but_not_set")
                            time.sleep(10)
                            continue
                        self.audit.log("SECURITY_CHECK", pin_ok=ok, cert_sha256=actual, pinned=bool(pin))
                    snap = read_host_snapshot()
                    send_msg(s, {
                        "auth": self.auth_token,
                        "role": "worker",
                        "version": "6.1",
                        "cpu_cores": self.cpu_cores,
                        "max_workers": self.max_workers,
                        "telemetry": snap,
                    })
                    self.audit.log("CONNECTION", host=self.master_host, tls=tls_enabled())
                    while not self.shutdown_flag:
                        if self.monitor.is_busy:
                            send_msg(s, {"status": "PAUSED_FOR_USER"})
                            time.sleep(3)
                            continue
                        payload = recv_msg(s)
                        if payload is None:
                            break
                        task = payload.get("task")
                        if task == "SHUTDOWN":
                            self.audit.log("SHUTDOWN", reason="master")
                            self.request_shutdown()
                            break
                        if task == "WAIT":
                            snap = read_host_snapshot()
                            send_msg(s, {
                                "status": "IDLE",
                                "heartbeat": True,
                                "telemetry": snap,
                            })
                            continue
                        if task == "PROCESS":
                            send_msg(s, run_fixed_op(str(payload.get("op") or "sha256"), payload.get("data")))
                            continue
                        if task == "BATCH_PROCESS":
                            batch = payload.get("data") or []
                            items = []
                            for i, entry in enumerate(batch):
                                if isinstance(entry, dict) and ("data" in entry or "op" in entry):
                                    items.append({
                                        "op": entry.get("op") or payload.get("op") or "sha256",
                                        "data": entry.get("data", entry),
                                        "id": entry.get("id", i),
                                    })
                                else:
                                    items.append({"op": payload.get("op") or "sha256", "data": entry, "id": i})
                            t0 = time.time()
                            results = list(self.pool.map(process_batch_item, items))
                            self.audit.log("BATCH_PROCESSED", size=len(items), duration_sec=round(time.time() - t0, 3))
                            send_msg(s, {"status": "BATCH_SUCCESS", "results": results})
                            continue
                        send_msg(s, {"status": "BLOCKED", "error": "unknown_task"})
            except socket.timeout:
                if not self.shutdown_flag:
                    self.audit.log("TIMEOUT")
                    time.sleep(5)
            except Exception as e:
                if not self.shutdown_flag:
                    self.audit.log("ERROR", reason=str(e))
                    time.sleep(10)
        try:
            self.pool.shutdown(wait=True, cancel_futures=False)
        except TypeError:
            self.pool.shutdown(wait=True)
        self.audit.log("WORKER_STOPPED")
        self.audit.close()


def main() -> None:
    print(f"Worker v6.0 prio={set_low_priority()} tls={tls_enabled()} pin={bool(expected_pin())}")
    host = os.environ.get("AURA_GRID_MASTER_HOST", "127.0.0.1")
    port = int(os.environ.get("AURA_GRID_MASTER_PORT", "5005"))
    worker = GridWorker(host, port)

    def _sig(_s, _f):
        worker.request_shutdown()

    signal.signal(signal.SIGINT, _sig)
    try:
        signal.signal(signal.SIGTERM, _sig)
    except Exception:
        pass
    worker.start()


if __name__ == "__main__":
    main()
