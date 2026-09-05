#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Auto-Heal Agent v1.0
Sistema de auto-cura proativa para Bridge, Engine, Voice e Desktop.
PAPER-TRADE ONLY.
"""
import os, sys, time, json, subprocess, psutil, requests
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)
REPORT_PATH = LOGDIR / "auto_heal_report.json"
MASTER_LOG = LOGDIR / "auto_heal.log"

SERVICES = {
    "Bridge": {"port": 8080, "health": "http://127.0.0.1:8080/health", "script": "bridge/server.py"},
    "Engine": {"port": 8765, "health": "http://127.0.0.1:8765/api/health", "script": "engine/server.py"},
    "Voice": {"port": 8099, "health": "http://127.0.0.1:8099/api/voice/health", "script": "bridge/jarvis_voice_server.py"},
}

PAPER_TRADE = os.environ.get("PAPER_TRADE", "true").lower() == "true"
EXECUTION_ALLOWED = os.environ.get("EXECUTION_ALLOWED", "false").lower() == "true"


def log(msg: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    with open(MASTER_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_health(name: str, url: str, timeout: int = 5) -> dict:
    try:
        r = requests.get(url, timeout=timeout)
        return {"name": name, "healthy": r.status_code == 200, "status": r.status_code, "latency_ms": int(r.elapsed.total_seconds() * 1000)}
    except Exception as e:
        return {"name": name, "healthy": False, "status": 0, "error": str(e)}


def kill_port_processes(port: int):
    killed = []
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr.port == port and conn.pid:
            try:
                p = psutil.Process(conn.pid)
                name = p.name()
                p.terminate()
                p.wait(timeout=3)
                killed.append({"pid": conn.pid, "name": name})
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                log(f"  [WARN] Nao foi possivel matar PID {conn.pid}: {e}")
    return killed


def start_service(name: str, config: dict) -> dict:
    venv_py = AURA_ROOT / "engine" / "venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        venv_py = Path(sys.executable)
    script_path = AURA_ROOT / config["script"]
    if not script_path.exists():
        return {"started": False, "error": f"Script nao encontrado: {script_path}"}
    env = os.environ.copy()
    env["AURA_ROOT"] = str(AURA_ROOT)
    env["PYTHONPATH"] = f"{AURA_ROOT};{AURA_ROOT}/engine;{AURA_ROOT}/bridge"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PAPER_TRADE"] = "true"
    env["EXECUTION_ALLOWED"] = "false"
    env["AURA_EXECUTION_ALLOWED"] = "0"
    env["AURA_UNLOCK_LIVE"] = "0"
    env["AURA_PAPER_ONLY"] = "1"
    env["GLM_ADVISORY_ONLY"] = "true"
    env["CUDA_VISIBLE_DEVICES"] = os.environ.get("CUDA_VISIBLE_DEVICES", "0")
    env["AURA_CUDA_DEVICE"] = os.environ.get("AURA_CUDA_DEVICE", "0")
    env["OLLAMA_NUM_GPU"] = os.environ.get("OLLAMA_NUM_GPU", "99")
    env["AURA_OLLAMA_KEEP_ALIVE"] = os.environ.get("AURA_OLLAMA_KEEP_ALIVE", "30m")
    env["AURA_HERMES_GPU"] = os.environ.get("AURA_HERMES_GPU", "1")
    port = config["port"]
    args = [str(venv_py), "-u", str(script_path), "--host", "127.0.0.1", "--port", str(port)]
    try:
        proc = subprocess.Popen(
            args, cwd=str(AURA_ROOT), env=env,
            stdout=open(LOGDIR / f"{name.lower()}_heal.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        time.sleep(3)
        return {"started": True, "pid": proc.pid}
    except Exception as e:
        return {"started": False, "error": str(e)}


def heal_service(name: str, config: dict) -> dict:
    log(f"[HEAL] Iniciando cura de {name}...")
    port = config["port"]
    killed = kill_port_processes(port)
    if killed:
        log(f"  [HEAL] Processos mortos na porta {port}: {killed}")
    time.sleep(1)
    result = start_service(name, config)
    if result["started"]:
        log(f"  [HEAL] {name} reiniciado (PID {result['pid']})")
        for i in range(20):
            time.sleep(1)
            h = check_health(name, config["health"], timeout=3)
            if h["healthy"]:
                log(f"  [HEAL] {name} health OK apos {i+1}s")
                return {"healed": True, "pid": result["pid"], "health": h}
        log(f"  [HEAL] {name} reiniciado mas health nao respondeu a tempo")
        return {"healed": False, "pid": result["pid"], "error": "health timeout"}
    else:
        log(f"  [HEAL] Falha ao reiniciar {name}: {result.get('error')}")
        return {"healed": False, "error": result.get("error")}


def check_gpu() -> dict:
    try:
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            gpus = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            mem = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10
            )
            mem_info = mem.stdout.strip() if mem.returncode == 0 else "N/A"
            return {"available": True, "gpus": gpus, "memory": mem_info}
    except FileNotFoundError:
        return {"available": False, "error": "nvidia-smi nao encontrado — fallback CPU"}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_desktop_process() -> dict:
    for proc in psutil.process_iter(["pid", "name"]):
        if "Aura.QuantX.Desktop" in proc.info["name"]:
            return {"running": True, "pid": proc.info["pid"], "name": proc.info["name"]}
    return {"running": False}


def main():
    log("=" * 60)
    log("AURA Auto-Heal Agent v1.0 iniciado")
    log(f"ROOT: {AURA_ROOT}")
    log(f"PAPER_TRADE={PAPER_TRADE} | EXECUTION_ALLOWED={EXECUTION_ALLOWED}")
    log("=" * 60)
    report = {
        "timestamp": datetime.now().isoformat(),
        "aura_root": str(AURA_ROOT),
        "paper_trade": PAPER_TRADE,
        "execution_allowed": EXECUTION_ALLOWED,
        "services": {},
        "gpu": check_gpu(),
        "desktop": check_desktop_process(),
        "actions": []
    }
    all_healthy = True
    for name, config in SERVICES.items():
        h = check_health(name, config["health"])
        report["services"][name] = h
        if h["healthy"]:
            log(f"[OK] {name}: healthy (latency={h.get('latency_ms', 'N/A')}ms)")
        else:
            log(f"[FALHA] {name}: {h.get('error', 'status ' + str(h.get('status', 'unknown')))}")
            all_healthy = False
            heal_result = heal_service(name, config)
            report["actions"].append({"service": name, "action": "heal", "result": heal_result})
    gpu = report["gpu"]
    if not gpu["available"]:
        log("[GPU] Fallback CPU — ajustando variaveis de ambiente")
        os.environ["AURA_HERMES_GPU"] = "0"
        os.environ["OLLAMA_NUM_GPU"] = "0"
        report["actions"].append({"action": "gpu_fallback_cpu", "reason": gpu.get("error")})
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(f"[RESUMO] Todos saudaveis: {all_healthy}")
    log(f"[RESUMO] Relatorio: {REPORT_PATH}")
    log("=" * 60)
    return 0 if all_healthy else 1


if __name__ == "__main__":
    sys.exit(main())
