#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Pre-Flight Check v1.0
Verificação pré-voo completa antes de iniciar o AURA Operator OS.
Valida dependências, permissões, portas, GPU, interface e segurança.
"""
import os, sys, json, subprocess, socket, psutil
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
REPORT_PATH = AURA_ROOT / "logs_supervisor" / "preflight_report.json"


def check(name: str, condition: bool, detail: str = "") -> dict:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return {"name": name, "pass": condition, "detail": detail}


def check_python() -> dict:
    v = sys.version_info
    ok = v.major == 3 and 10 <= v.minor <= 11
    return check("Python 3.10/3.11", ok, f"{v.major}.{v.minor}.{v.micro}")


def check_venv() -> dict:
    venv = AURA_ROOT / "engine" / "venv" / "Scripts" / "python.exe"
    return check("Venv existe", venv.exists(), str(venv))


def check_dependencies() -> dict:
    required = ["requests", "pydantic", "fastapi", "uvicorn", "httpx", "psutil"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return check("Dependências críticas", len(missing) == 0, f"faltando: {missing}" if missing else "OK")


def check_ports() -> dict:
    ports = [8080, 8765, 8099, 8766, 9101]
    occupied = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                occupied.append(port)
    return check("Portas livres", len(occupied) == 0, f"ocupadas: {occupied}" if occupied else "todas livres")


def check_gpu() -> dict:
    try:
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        ok = result.returncode == 0
        detail = result.stdout.strip().split("\n")[0] if ok else "NVIDIA não detectada"
        return check("GPU NVIDIA", ok, detail)
    except FileNotFoundError:
        return check("GPU NVIDIA", False, "nvidia-smi não encontrado — fallback CPU")


def check_interface() -> dict:
    idx = AURA_ROOT / "desktop" / "ui" / "matriz_v22" / "index.html"
    return check("Interface V25Q", idx.exists(), str(idx))


def check_desktop_exe() -> dict:
    exe = AURA_ROOT / "desktop" / "publish" / "Aura.QuantX.Desktop.exe"
    return check("Desktop EXE", exe.exists(), str(exe))


def check_engine() -> dict:
    engine = AURA_ROOT / "engine" / "server.py"
    return check("Engine server.py", engine.exists(), str(engine))


def check_bridge() -> dict:
    bridge = AURA_ROOT / "bridge" / "server.py"
    return check("Bridge server.py", bridge.exists(), str(bridge))


def check_security_invariants() -> dict:
    env = os.environ
    checks = {
        "PAPER_TRADE": env.get("PAPER_TRADE", "").lower() == "true",
        "EXECUTION_ALLOWED": env.get("EXECUTION_ALLOWED", "").lower() == "false",
    }
    ok = all(checks.values())
    return check("Invariantes de segurança", ok, str(checks))


def check_disk_space() -> dict:
    disk = psutil.disk_usage(str(AURA_ROOT))
    free_gb = disk.free // (1024 ** 3)
    ok = free_gb >= 2
    return check("Espaço em disco", ok, f"{free_gb} GB livres")


def check_memory() -> dict:
    mem = psutil.virtual_memory()
    ok = mem.available >= 2 * 1024 * 1024 * 1024  # 2GB
    return check("Memória disponível", ok, f"{mem.available // (1024**2)} MB livres")


def main():
    print("=" * 60)
    print("AURA Pre-Flight Check v1.0")
    print("=" * 60)

    checks = [
        check_python(),
        check_venv(),
        check_dependencies(),
        check_ports(),
        check_gpu(),
        check_interface(),
        check_desktop_exe(),
        check_engine(),
        check_bridge(),
        check_security_invariants(),
        check_disk_space(),
        check_memory(),
    ]

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)

    report = {
        "timestamp": datetime.now().isoformat(),
        "aura_root": str(AURA_ROOT),
        "passed": passed,
        "total": total,
        "all_pass": passed == total,
        "checks": checks,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"RESULTADO: {passed}/{total} verificações passaram")
    if passed == total:
        print("✅ TUDO PRONTO — AURA pode decolar!")
    else:
        print("❌ HÁ FALHAS — Corrija antes de iniciar o AURA")
    print(f"Relatório: {REPORT_PATH}")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
