#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Monitor v2.0
Monitoramento contínuo de serviços, captura, telemetria e alertas.
"""
import os, sys, time, json, requests, psutil
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
LOGDIR = AURA_ROOT / "logs_supervisor"
LOGDIR.mkdir(exist_ok=True)
STATE_PATH = LOGDIR / "monitor_state.json"
ALERT_PATH = LOGDIR / "monitor_alerts.jsonl"
LOG_PATH = LOGDIR / "monitor.log"

INTERVAL = int(os.environ.get("AURA_MONITOR_INTERVAL", "30"))
MAX_ALERTS = 100

ENDPOINTS = {
    "Bridge": "http://127.0.0.1:8080/health",
    "Engine": "http://127.0.0.1:8765/api/health",
    "Engine_UI_State": "http://127.0.0.1:8765/api/ui/state",
    "Voice": "http://127.0.0.1:8099/api/voice/health",
    "Bridge_Feed": "http://127.0.0.1:8080/api/cornerai/feed/latest",
}


def log(msg: str):
    ts = datetime.now().isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_endpoint(name: str, url: str, timeout: int = 5) -> dict:
    try:
        r = requests.get(url, timeout=timeout)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"status_text": r.text[:200]}
        return {"name": name, "url": url, "healthy": r.status_code == 200, "status_code": r.status_code, "latency_ms": int(r.elapsed.total_seconds() * 1000), "data": data}
    except requests.exceptions.ConnectionError:
        return {"name": name, "url": url, "healthy": False, "error": "connection_refused"}
    except requests.exceptions.Timeout:
        return {"name": name, "url": url, "healthy": False, "error": "timeout"}
    except Exception as e:
        return {"name": name, "url": url, "healthy": False, "error": str(e)}


def check_system_resources() -> dict:
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    disk = psutil.disk_usage(str(AURA_ROOT))
    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_available_mb": mem.available // (1024 * 1024),
        "disk_free_gb": disk.free // (1024 ** 3),
        "disk_percent": disk.percent,
    }


def check_capture_flow() -> dict:
    try:
        r = requests.get(ENDPOINTS["Bridge_Feed"], timeout=5)
        if r.status_code == 200:
            data = r.json()
            has_fixture = bool(data.get("fixture_id") or data.get("home_team"))
            return {"has_feed": True, "has_fixture": has_fixture, "sample_keys": list(data.keys())[:10]}
        return {"has_feed": False, "status": r.status_code}
    except Exception as e:
        return {"has_feed": False, "error": str(e)}


def write_alert(alert: dict):
    with open(ALERT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(alert, ensure_ascii=False) + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"cycle": 0, "alerts_count": 0, "last_alert_time": None}


def save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def run_cycle(state: dict) -> dict:
    cycle = state.get("cycle", 0) + 1
    log(f"--- Ciclo {cycle} ---")
    report = {
        "timestamp": datetime.now().isoformat(),
        "cycle": cycle,
        "endpoints": {},
        "system": check_system_resources(),
        "capture": check_capture_flow(),
        "alerts": []
    }
    for name, url in ENDPOINTS.items():
        if name == "Bridge_Feed":
            continue
        result = check_endpoint(name, url)
        report["endpoints"][name] = result
        if not result["healthy"]:
            alert = {"type": "service_down", "service": name, "cycle": cycle, "detail": result.get("error", "unknown")}
            report["alerts"].append(alert)
            write_alert(alert)
            log(f"  [ALERTA] {name} INDISPONIVEL: {result.get('error', 'status ' + str(result.get('status_code', '?')))}")
        else:
            log(f"  [OK] {name}: OK ({result['latency_ms']}ms)")
    sys_res = report["system"]
    if sys_res["memory_percent"] > 90:
        alert = {"type": "high_memory", "cycle": cycle, "value": sys_res["memory_percent"]}
        report["alerts"].append(alert)
        write_alert(alert)
        log(f"  [ALERTA] Memoria alta: {sys_res['memory_percent']}%")
    if sys_res["cpu_percent"] > 95:
        alert = {"type": "high_cpu", "cycle": cycle, "value": sys_res["cpu_percent"]}
        report["alerts"].append(alert)
        write_alert(alert)
        log(f"  [ALERTA] CPU alta: {sys_res['cpu_percent']}%")
    cap = report["capture"]
    if not cap.get("has_feed"):
        alert = {"type": "no_capture_feed", "cycle": cycle, "detail": cap.get("error", "no_data")}
        report["alerts"].append(alert)
        write_alert(alert)
        log(f"  [ALERTA] Sem feed de captura: {cap.get('error', 'dados vazios')}")
    else:
        log(f"  [OK] Captura: feed ativo (fixture={cap.get('has_fixture', False)})")
    state["cycle"] = cycle
    state["last_check"] = datetime.now().isoformat()
    state["alerts_count"] = state.get("alerts_count", 0) + len(report["alerts"])
    return report


def main():
    log("=" * 60)
    log("AURA Monitor v2.0 iniciado")
    log(f"Intervalo: {INTERVAL}s | ROOT: {AURA_ROOT}")
    log("=" * 60)
    state = load_state()
    try:
        while True:
            report = run_cycle(state)
            save_state(state)
            cycle_path = LOGDIR / f"monitor_cycle_{state['cycle']}.json"
            with open(cycle_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        log("[MONITOR] Interrompido pelo usuario")
        save_state(state)
        return 0


if __name__ == "__main__":
    sys.exit(main())
