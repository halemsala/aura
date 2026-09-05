"""Arranque/paragem/status idempotente. Usado pelos BATs. Nunca abre o browser."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import paths
from .config import get_config

ROOT = paths.PROJECT_ROOT
LOG_DIR = ROOT / "logs_supervisor" / "grok_audit"
HERMES_LOG = ROOT / "logs_supervisor" / "hermes_v10.log"
ALFRED_STDOUT = paths.DATA_ROOT / "stdout.log"
ALFRED_STDERR = paths.DATA_ROOT / "stderr.log"
HERMES_PID = ROOT / "logs_supervisor" / "hermes.pid"
START_LOG = LOG_DIR / "start_all.log"


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print(line)
    with START_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _pid_on_port(port: int):
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"], text=True, timeout=8, errors="replace")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    needle = f"127.0.0.1:{port}"
    for line in out.splitlines():
        if needle in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    return None
    return None


def _http_json(url: str, timeout: float = 3):
    import requests
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _alive(url: str, timeout: float = 3) -> bool:
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        return r.ok
    except Exception:  # noqa: BLE001
        return False


def _kill_pid(pid: int, reason: str) -> None:
    if not pid:
        return
    _log(f"a terminar PID {pid} ({reason})")
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def _wait_health(url: str, seconds: int = 25) -> bool:
    for _ in range(seconds):
        if _alive(url, timeout=2):
            return True
        time.sleep(1)
    return False


def _check_python() -> None:
    _log(f"python {sys.version.split()[0]} {sys.executable}")
    missing = []
    for mod in ("fastapi", "uvicorn", "pydantic", "requests"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(f"dependências em falta: {', '.join(missing)} — pip install -r requirements-alfred.txt")


def _check_ollama(cfg: dict) -> None:
    import requests
    url = cfg["ollama_url"].rstrip("/") + "/api/tags"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        names = [m.get("name") for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Ollama offline em {url}: {e}")
    if "qwen3:8b" not in names:
        raise SystemExit(f"qwen3:8b ausente em /api/tags. Modelos: {names}")
    _log("ollama qwen3:8b OK")


def _spawn_detached(title: str, inner_cmd: str, cwd: Path) -> None:
    """No Windows usa `start "titulo"` para sair do Job Object e sobreviver ao BAT pai."""
    if os.name == "nt":
        cmdline = f'start "{title}" /MIN cmd /c {inner_cmd}'
        subprocess.Popen(cmdline, cwd=str(cwd), shell=True)
        return
    log = (LOG_DIR / "detached.log").open("a", encoding="utf-8")
    subprocess.Popen(inner_cmd, cwd=str(cwd), shell=True, stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)


def _start_alfred(cfg: dict) -> None:
    health = f"http://{cfg['host']}:{cfg['port']}/health"
    if _alive(health):
        _log(f"Alfred já online em {health}")
        return
    pid = _pid_on_port(int(cfg["port"]))
    if pid:
        _kill_pid(pid, "Alfred duplicado sem /health")
        time.sleep(1)
    ALFRED_STDOUT.parent.mkdir(parents=True, exist_ok=True)
    inner = (
        f'{sys.executable} -m alfred.api --host {cfg["host"]} --port {cfg["port"]} '
        f'>> "{ALFRED_STDOUT}" 2>> "{ALFRED_STDERR}"'
    )
    _spawn_detached("AURA-Alfred", inner, ROOT)
    _log("Alfred lançado (start /MIN)")
    if not _wait_health(health, 25):
        raise SystemExit(f"Alfred não respondeu em {health}. Log: {ALFRED_STDERR}")
    _log("Alfred /health OK")


def _start_hermes() -> None:
    health = "http://127.0.0.1:8777/health"
    if _alive(health):
        _log("Hermes já online em :8777")
        return
    pid = _pid_on_port(8777)
    if pid:
        _kill_pid(pid, "Hermes duplicado sem /health")
        time.sleep(1)
    script = ROOT / "hermes_v10" / "scripts" / "hermes_v10_chat_api.py"
    if not script.is_file():
        raise SystemExit(f"falta {script}")
    HERMES_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AURA_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT / "hermes_v10") + os.pathsep + str(ROOT)
    env["PAPER_TRADE"] = "true"
    env["EXECUTION_ALLOWED"] = "false"
    env["PYTHONUTF8"] = "1"
    env["AURA_NO_BROWSER"] = "1"
    inner = (
        f'set AURA_ROOT={ROOT}& set PYTHONPATH={ROOT}\\hermes_v10;{ROOT}& '
        f'set PAPER_TRADE=true& set EXECUTION_ALLOWED=false& set PYTHONUTF8=1& set AURA_NO_BROWSER=1& '
        f'{sys.executable} -u {script} >> "{HERMES_LOG}" 2>&1'
    )
    os.environ.update({k: env[k] for k in ("AURA_ROOT", "PYTHONPATH", "PAPER_TRADE",
                                           "EXECUTION_ALLOWED", "PYTHONUTF8", "AURA_NO_BROWSER")})
    _spawn_detached("AURA-Hermes-Chat", inner, ROOT / "hermes_v10")
    _log("Hermes lançado (start /MIN)")
    if not _wait_health(health, 30):
        raise SystemExit(f"Hermes não respondeu em {health}. Log: {HERMES_LOG}")
    _log("Hermes /health OK")


def cmd_start() -> int:
    cfg = get_config()
    _log(f"START root={ROOT}")
    if not (ROOT / "alfred" / "api.py").is_file():
        raise SystemExit(f"C:\\aura não parece a raiz (falta alfred\\api.py). CD={ROOT}")
    _check_python()
    _check_ollama(cfg)
    _start_alfred(cfg)
    _start_hermes()
    _log("arranque concluído — browser NÃO aberto")
    print("Chat: AURA_OPEN_CHAT.bat  (http://127.0.0.1:8777/chat)")
    print("Alfred:", f"http://{cfg['host']}:{cfg['port']}/health")
    print("Log:", START_LOG)
    return 0


def cmd_stop() -> int:
    cfg = get_config()
    from . import service as service_mod
    print(json.dumps(service_mod.stop_registered(), ensure_ascii=False))
    for port, name in ((int(cfg["port"]), "alfred"), (8777, "hermes")):
        pid = _pid_on_port(port)
        if pid:
            _kill_pid(pid, name)
    try:
        if HERMES_PID.exists():
            HERMES_PID.unlink()
    except OSError:
        pass
    _log("stop concluído (Ollama não foi tocado)")
    return 0


def cmd_status() -> int:
    cfg = get_config()
    rows = []
    for name, url in (
        ("ollama", cfg["ollama_url"].rstrip("/") + "/api/tags"),
        ("alfred", f"http://{cfg['host']}:{cfg['port']}/health"),
        ("hermes", "http://127.0.0.1:8777/health"),
    ):
        try:
            data = _http_json(url, timeout=4)
            if name == "ollama":
                names = [m.get("name") for m in data.get("models", [])]
                rows.append({"service": name, "ok": "qwen3:8b" in names, "detail": names[:8]})
            else:
                rows.append({"service": name, "ok": True, "detail": data})
        except Exception as e:  # noqa: BLE001
            rows.append({"service": name, "ok": False, "detail": str(e)[:200]})
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0 if all(r["ok"] for r in rows) else 1


def cmd_alfred_command(message: str) -> int:
    cfg = get_config()
    import requests
    url = f"http://{cfg['host']}:{cfg['port']}/ask"
    try:
        r = requests.post(url, json={"message": message, "session_id": "bat"}, timeout=90)
    except Exception as e:  # noqa: BLE001
        print(f"Alfred indisponível: {e}")
        return 2
    print(r.text)
    return 0 if r.ok else 1


def cmd_rollback() -> int:
    from .checkpoint_cli import restore_last
    from .tools.patch import _last_patch, rollback_last
    from .executor import Context
    last = _last_patch("")
    if last:
        out = rollback_last({}, Context("rollback-bat", authorized=True, token_ok=True))
    else:
        out = restore_last()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if not out.get("error") else 1


def main():
    ap = argparse.ArgumentParser(prog="alfred.boot")
    ap.add_argument("command", choices=["start", "stop", "status", "ask", "rollback"])
    ap.add_argument("message", nargs="*", default=[])
    a = ap.parse_args()
    os.chdir(str(ROOT))
    if a.command == "start":
        return cmd_start()
    if a.command == "stop":
        return cmd_stop()
    if a.command == "status":
        return cmd_status()
    if a.command == "ask":
        msg = " ".join(a.message).strip()
        if not msg:
            raise SystemExit("uso: python -m alfred.boot ask Alfred, estado")
        return cmd_alfred_command(msg)
    if a.command == "rollback":
        return cmd_rollback()
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as e:
        if e.code not in (0, None):
            print("Log:", START_LOG)
        raise
