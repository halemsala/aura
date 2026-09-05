"""Mantém Alfred (:8791) e Hermes (:8777) vivos.
Nunca toca no Ollama. Circuit breaker: 3 falhas/15 min → pausa 5 min.
Correr: pythonw -m alfred.supervise
"""
import os
import sys
import time
import json
import signal
import subprocess
from pathlib import Path

from . import circuit, paths
from .config import get_config

ROOT = paths.PROJECT_ROOT
LOG = ROOT / "logs_supervisor" / "grok_audit" / "supervise.log"
PID_PATH = paths.DATA_ROOT / "supervise.pid"
ALFRED_OUT = paths.DATA_ROOT / "stdout.log"
ALFRED_ERR = paths.DATA_ROOT / "stderr.log"
HERMES_LOG = ROOT / "logs_supervisor" / "hermes_v10.log"
INTERVAL = 8
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _alive(url: str) -> bool:
    try:
        import requests
        return requests.get(url, timeout=3).ok
    except Exception:  # noqa: BLE001
        return False


def _pid_on_port(port: int):
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"], text=True, timeout=8, errors="replace")
    except Exception:
        return None
    needle = f"127.0.0.1:{port}"
    for line in out.splitlines():
        if needle in line and "LISTENING" in line.upper():
            try:
                return int(line.split()[-1])
            except ValueError:
                return None
    return None


def _spawn(argv, cwd, out_path, err_path, env=None) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    out = open(out_path, "a", encoding="utf-8")
    err = out if str(err_path) == str(out_path) else open(err_path, "a", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    subprocess.Popen(argv, cwd=str(cwd), stdout=out, stderr=err, env=env,
                     creationflags=flags, start_new_session=(os.name != "nt"))


def _start_alfred(cfg) -> None:
    if _alive(f"http://{cfg['host']}:{cfg['port']}/health"):
        return
    gate = circuit.allow("supervise:alfred")
    if not gate["allowed"]:
        _log(f"alfred circuit open retry_in={gate.get('retry_in_s')}")
        return
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(ROOT / "bridge")
    env["AURA_ROOT"] = str(ROOT)
    env["AURA_TTS_ENGINE"] = "edge"
    env["KANTEIRO_NEURAL_VOICE"] = "pt-BR-HumbertoNeural"
    env["KANTEIRO_NEURAL_PITCH"] = env.get("KANTEIRO_NEURAL_PITCH") or "-18Hz"
    env["KANTEIRO_NEURAL_RATE"] = env.get("KANTEIRO_NEURAL_RATE") or "-15%"
    env["OLLAMA_KEEP_ALIVE"] = env.get("OLLAMA_KEEP_ALIVE") or "-1"
    env["PYTHONUTF8"] = "1"
    _spawn(
        [sys.executable, "-m", "alfred.api", "--host", cfg["host"], "--port", str(cfg["port"])],
        ROOT, ALFRED_OUT, ALFRED_ERR, env=env)
    _log("alfred spawn")


def _start_voice() -> None:
    if _alive("http://127.0.0.1:8099/api/voice/health") or _alive("http://127.0.0.1:8099/health"):
        return
    script = ROOT / "bridge" / "jarvis_voice_server.py"
    if not script.is_file():
        return
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    env["AURA_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT / "bridge") + os.pathsep + str(ROOT)
    env["AURA_TTS_ENGINE"] = "edge"
    env["KANTEIRO_NEURAL_VOICE"] = "pt-BR-HumbertoNeural"
    env["KANTEIRO_NEURAL_PITCH"] = "-18Hz"
    env["KANTEIRO_NEURAL_RATE"] = "-15%"
    env["AURA_NO_BROWSER"] = "1"
    env["PYTHONUTF8"] = "1"
    log = ROOT / "logs_supervisor" / "voice_supervise.log"
    _spawn([sys.executable, "-u", str(script), "--host", "127.0.0.1", "--port", "8099", "--lazy"],
           ROOT / "bridge", log, log, env=env)
    _log("voice spawn")


def _start_hermes() -> None:
    if _alive("http://127.0.0.1:8777/health"):
        return
    gate = circuit.allow("supervise:hermes")
    if not gate["allowed"]:
        _log(f"hermes circuit open retry_in={gate.get('retry_in_s')}")
        return
    script = ROOT / "hermes_v10" / "scripts" / "hermes_v10_chat_api.py"
    env = os.environ.copy()
    env["AURA_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = str(ROOT / "hermes_v10") + os.pathsep + str(ROOT)
    try:
        from .flags import load_flags
        env["PAPER_TRADE"] = "true" if load_flags().get("paper_trade", True) else "false"
    except Exception:
        env["PAPER_TRADE"] = "true"
    env["EXECUTION_ALLOWED"] = "false"
    env["PYTHONUTF8"] = "1"
    env["AURA_NO_BROWSER"] = "1"
    env["OLLAMA_KEEP_ALIVE"] = "-1"
    env["AURA_OLLAMA_NUM_CTX"] = "3072"
    env["AURA_OLLAMA_NUM_PREDICT"] = "1024"
    env["AURA_OLLAMA_TEMPERATURE"] = "0.30"
    env["OLLAMA_NUM_GPU"] = "99"
    _spawn([sys.executable, "-u", str(script)], ROOT / "hermes_v10",
           HERMES_LOG, HERMES_LOG, env=env)
    _log("hermes spawn")


def _write_pid() -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def already_running() -> bool:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if os.name == "nt":
        out = os.popen(f'tasklist /FI "PID eq {pid}" /NH').read()
        return str(pid) in out and "python" in out.lower()
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def launch_supervisor() -> dict:
    """Arranca pythonw -m alfred.supervise se ainda não existir."""
    if already_running() and _alive("http://127.0.0.1:8791/health"):
        return {"supervisor": "already", "pid": PID_PATH.read_text(encoding="utf-8").strip()}
    py = Path(sys.executable)
    pythonw = py.with_name("pythonw.exe") if py.name.lower() == "python.exe" and py.with_name("pythonw.exe").is_file() else py
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(ROOT / "bridge")
    env["AURA_ROOT"] = str(ROOT)
    env["AURA_TTS_ENGINE"] = "edge"
    env["KANTEIRO_NEURAL_VOICE"] = "pt-BR-HumbertoNeural"
    flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW if os.name == "nt" else 0
    p = subprocess.Popen(
        [str(pythonw), "-m", "alfred.supervise"],
        cwd=str(ROOT), env=env, creationflags=flags,
        start_new_session=(os.name != "nt"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"supervisor": "started", "pid": p.pid}


def loop() -> None:
    _write_pid()
    _log(f"supervise start pid={os.getpid()}")
    cfg = get_config()
    while True:
        try:
            aurl = f"http://{cfg['host']}:{cfg['port']}/health"
            if _alive(aurl):
                circuit.record_success("supervise:alfred")
            else:
                _start_alfred(cfg)
                time.sleep(3)
                if not _alive(aurl):
                    circuit.record_failure("supervise:alfred")
            if _alive("http://127.0.0.1:8777/health"):
                circuit.record_success("supervise:hermes")
            else:
                _start_hermes()
                time.sleep(3)
                if not _alive("http://127.0.0.1:8777/health"):
                    circuit.record_failure("supervise:hermes")
            if _alive("http://127.0.0.1:8099/api/voice/health") or _alive("http://127.0.0.1:8099/health"):
                circuit.record_success("supervise:voice")
            else:
                _start_voice()
                time.sleep(3)
        except Exception as e:  # noqa: BLE001
            _log(f"loop error {type(e).__name__}: {e}")
        time.sleep(INTERVAL)


def main() -> int:
    os.chdir(str(ROOT))
    if already_running():
        _log("já existe supervisor — a sair")
        return 0
    loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
