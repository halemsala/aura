"""Snapshot comparável de desempenho local do AURA, sem efeitos colaterais.

Execute antes e depois de iniciar o AURA no Windows. O resultado é uma
medição pontual, não uma prova de estabilidade, ausência de BSOD ou ganho
causal. O SQLite é aberto em modo somente leitura.
"""
from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "engine" / "aura_quant_x.db"


def _gpu_snapshot() -> dict[str, Any]:
    command = ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
        raw = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
        values = [item.strip() for item in raw.split(",")]
        if completed.returncode != 0 or len(values) != 3:
            return {"available": False, "reason": "nvidia_smi_failed"}
        return {"available": True, "memory_used_mb": float(values[0]), "memory_total_mb": float(values[1]), "utilization_percent": float(values[2])}
    except FileNotFoundError:
        return {"available": False, "reason": "nvidia_smi_missing"}
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}


def _host_snapshot() -> dict[str, Any]:
    try:
        import psutil
        return {
            "psutil": True,
            "cpu_percent_sample": psutil.cpu_percent(interval=0.5),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_available_mb": round(psutil.virtual_memory().available / (1024 * 1024), 1),
        }
    except ImportError:
        return {"psutil": False, "reason": "psutil_missing"}
    except Exception as exc:
        return {"psutil": False, "reason": type(exc).__name__}


def _db_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "state": "ABSENT"}
    try:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=2) as connection:
            pragmas = {
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone()[0],
                "synchronous": connection.execute("PRAGMA synchronous").fetchone()[0],
                "cache_size": connection.execute("PRAGMA cache_size").fetchone()[0],
                "busy_timeout": connection.execute("PRAGMA busy_timeout").fetchone()[0],
            }
        return {"available": True, "state": "ONLINE", "size_mb": round(path.stat().st_size / (1024 * 1024), 3), "pragmas": pragmas}
    except (OSError, sqlite3.Error) as exc:
        return {"available": False, "state": "ERROR", "reason": type(exc).__name__}


def collect_snapshot(db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    started = time.monotonic()
    return {
        "ok": True,
        "benchmark": "AURA_PERFORMANCE_READ_ONLY_V1",
        "timestamp_unix": time.time(),
        "platform": {"system": platform.system(), "release": platform.release()[:80], "architecture": platform.machine()[:40], "python": platform.python_version()},
        "host": _host_snapshot(),
        "gpu": _gpu_snapshot(),
        "database": _db_snapshot(Path(db_path)),
        "policy": "READ_ONLY_NO_COMMAND_EXECUTION",
        "paper_trade_only": True,
        "execution_allowed": False,
        "collection_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Banco canônico para consulta read-only")
    parser.add_argument("--json", action="store_true", help="Emitir JSON compacto")
    args = parser.parse_args()
    payload = collect_snapshot(args.db)
    print(json.dumps(payload, ensure_ascii=False, indent=0 if args.json else 2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

