#!/usr/bin/env python3
"""
AURA QUANT-X — System Prerequisites Checker
Fail-fast validation before install or start. Deterministic and idempotent.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

MIN_PYTHON = (3, 10)
MAX_PYTHON_MINOR = 11  # 3.10 or 3.11 only
MIN_RAM_GB = 16
MIN_DISK_FREE_GB = 20


def log_pass(msg: str) -> None:
    print(f"[PASS] {msg}")


def log_fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def log_warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def check_python_version() -> bool:
    current = sys.version_info
    msg = f"Python {current.major}.{current.minor}.{current.micro}"
    if current.major == MIN_PYTHON[0] and MIN_PYTHON[1] <= current.minor <= MAX_PYTHON_MINOR:
        log_pass(f"{msg} (required 3.10.x or 3.11.x)")
        return True
    log_fail(f"{msg} (required 3.10.x or 3.11.x)")
    return False


def check_ram() -> bool:
    try:
        system = platform.system()
        if system == "Windows":
            out = subprocess.check_output(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            lines = [ln.strip() for ln in out.splitlines() if ln.strip().isdigit()]
            if lines:
                ram_gb = int(lines[0]) / (1024**3)
            else:
                log_warn("Could not parse RAM via wmic; skipping strict check")
                return True
        elif system == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        ram_gb = int(line.split()[1]) / (1024**2)
                        break
                else:
                    log_warn("MemTotal not found")
                    return True
        elif system == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            ram_gb = int(out.strip()) / (1024**3)
        else:
            log_warn(f"RAM check skipped on {system}")
            return True

        if ram_gb >= MIN_RAM_GB:
            log_pass(f"RAM {ram_gb:.1f} GB (min {MIN_RAM_GB} GB)")
            return True
        log_fail(f"RAM {ram_gb:.1f} GB (min {MIN_RAM_GB} GB)")
        return False
    except Exception as exc:
        log_warn(f"RAM check error: {exc}")
        return True


def check_disk() -> bool:
    try:
        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024**3)
        if free_gb >= MIN_DISK_FREE_GB:
            log_pass(f"Disk free {free_gb:.1f} GB (min {MIN_DISK_FREE_GB} GB)")
            return True
        log_fail(f"Disk free {free_gb:.1f} GB (min {MIN_DISK_FREE_GB} GB)")
        return False
    except Exception as exc:
        log_warn(f"Disk check error: {exc}")
        return True


def check_gpu() -> None:
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            log_pass(f"NVIDIA GPU: {out.strip()}")
        except Exception as exc:
            log_warn(f"nvidia-smi present but query failed: {exc}")
    else:
        log_warn("nvidia-smi not found — GPU acceleration disabled (CPU mode OK)")


def main() -> int:
    print("=" * 50)
    print("  AURA QUANT-X — PREREQUISITES AUDIT")
    print("=" * 50)
    ok = True
    ok &= check_python_version()
    ok &= check_ram()
    ok &= check_disk()
    check_gpu()
    print("-" * 50)
    if ok:
        print("[OK] Critical prerequisites met. Ready for install/start.")
        return 0
    print("[ABORT] Critical prerequisite failure. Fix environment and retry.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
