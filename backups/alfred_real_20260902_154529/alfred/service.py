"""Gestão do processo do serviço Alfred: PID registado, stop/status.
Usado pelos BATs. Nunca usa wmic; nunca mata PIDs não registados."""
import argparse, atexit, json, os, signal, sys, time
from . import paths


def write_pid():
    paths.PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(clear_pid)


def clear_pid():
    try:
        if paths.PID_PATH.exists():
            current = paths.PID_PATH.read_text(encoding="utf-8").strip()
            if current == str(os.getpid()):
                paths.PID_PATH.unlink()
    except OSError:
        pass


def read_pid():
    try:
        return int(paths.PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def is_running(pid) -> bool:
    if not pid:
        return False
    pid = int(pid)
    if os.name == "nt":
        out = os.popen(f'tasklist /FI "PID eq {pid}" /NH').read()  # sem wmic
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_registered(timeout: float = 8.0) -> dict:
    pid = read_pid()
    if not pid:
        return {"stopped": False, "reason": "nenhum PID registado — o serviço não parece estar a correr"}
    if not is_running(pid):
        try:
            paths.PID_PATH.unlink()
        except OSError:
            pass
        return {"stopped": False, "reason": f"PID {pid} registado mas inactivo; registo limpo"}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        return {"stopped": False, "reason": f"falha ao sinalizar PID {pid}: {e}"}
    for _ in range(int(timeout * 10)):
        if not is_running(pid):
            try:
                paths.PID_PATH.unlink()
            except OSError:
                pass
            return {"stopped": True, "pid": pid}
        time.sleep(0.1)
    try:
        os.kill(pid, 9)  # último recurso — ainda assim, só ao PID registado
    except OSError:
        pass
    try:
        paths.PID_PATH.unlink()
    except OSError:
        pass
    return {"stopped": True, "pid": pid, "forced": True}


def main():
    ap = argparse.ArgumentParser(prog="alfred.service")
    ap.add_argument("command", choices=["status", "stop"])
    a = ap.parse_args()
    if a.command == "stop":
        print(json.dumps(stop_registered(), ensure_ascii=False))
        sys.exit(0)
    pid = read_pid()
    alive = bool(pid and is_running(pid))
    print(f"Alfred PID: {pid or '-'} | activo: {alive}")
    try:
        import requests
        from .config import get_config
        cfg = get_config()
        r = requests.get(f"http://{cfg['host']}:{cfg['port']}/health", timeout=3)
        print(f"HTTP /health ({cfg['host']}:{cfg['port']}):", r.status_code)
        print(r.text[:400])
    except Exception as e:  # noqa: BLE001
        print("HTTP /health: INDISPONIVEL:", e)
    sys.exit(0 if alive else 1)


if __name__ == "__main__":
    main()
