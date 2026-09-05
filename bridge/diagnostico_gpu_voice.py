"""Auditoria AURA QUANT-X ponta a ponta.

Uso:
  python diagnostico_gpu_voice.py
  python diagnostico_gpu_voice.py --deep

O modo padrão é rápido e somente leitura. --deep tenta carregar Whisper tiny
em CUDA/FP16 quando o ambiente permite, o que pode consumir memória e tempo.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "bridge"
ENGINE = ROOT / "engine"
REPORT_JSON = BRIDGE / "AURA_DIAGNOSTIC_REPORT.json"
REPORT_TXT = BRIDGE / "AURA_DIAGNOSTIC_REPORT.txt"
TARGET_MODEL = os.getenv("CORNERAI_MODEL", "llama3.2:3b")


def run(cmd, timeout=15, cwd: Optional[Path] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or ROOT),
            shell=isinstance(cmd, str),
            errors="replace",
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as exc:
        return 99, str(exc)


def http(url: str, timeout=4) -> Tuple[Optional[int], str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AURA-Diagnostic/12.6.17"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read(3000).decode("utf-8", "replace")
    except Exception as exc:
        return None, str(exc)


def tcp_open(port: int, host="127.0.0.1", timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def find_ollama() -> Optional[str]:
    candidates = [
        shutil.which("ollama"),
        shutil.which("ollama.exe"),
        os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.getenv("ProgramFiles", ""), "Ollama", "ollama.exe"),
        r"C:\Windows\System32\ollama.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return None


results: List[Dict[str, Any]] = []


def check(label: str, status: str, detail: str, critical: bool = True) -> None:
    if status not in {"ok", "warn", "fail", "skip"}:
        status = "warn"
    tag = {"ok": "OK   ", "warn": "WARN ", "fail": "FAIL ", "skip": "SKIP "}[status]
    print(f"[{tag}] {label:<28} {detail}")
    results.append({"label": label, "status": status, "detail": detail, "critical": critical})


def check_python_env(label: str, path: Path, imports: str) -> None:
    if not path.exists():
        check(label, "fail", f"Python ausente: {path}")
        return
    rc, out = run([str(path), "-c", imports], timeout=45)
    check(label, "ok" if rc == 0 else "fail", out[-500:] if out else "sem saída")


def check_log(label: str, paths: List[Path]) -> None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        check(label, "warn", "nenhum log criado ainda", critical=False)
        return
    chosen = max(existing, key=lambda p: p.stat().st_mtime)
    tail = chosen.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
    joined = " | ".join(tail[-4:])
    severe = any(x in joined.lower() for x in ("traceback", "fatal", "modulenotfounderror", "address already in use", "errno 98", "errno 10048"))
    check(label, "fail" if severe else "ok", f"{chosen.name} · {joined[-420:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="tenta smoke real do Whisper CUDA")
    args = parser.parse_args()

    print("AURA QUANT-X 12.6.17 — AUDITORIA PONTA A PONTA")
    print("=" * 78)
    print(f"Raiz: {ROOT}")
    print(f"Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    check("Python do diagnóstico", "ok" if sys.version_info >= (3, 10) else "fail", platform.python_version())
    check("Pacote/raiz", "ok" if ROOT.exists() else "fail", str(ROOT))
    check("PowerShell/Windows", "ok" if os.name == "nt" else "warn", f"os={os.name}", critical=False)

    nvidia = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if nvidia:
        rc, out = run([nvidia, "--query-gpu=name,driver_version,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"], timeout=15)
        check("NVIDIA/VRAM", "ok" if rc == 0 and out else "warn", out.splitlines()[0] if out else "nvidia-smi sem resposta", critical=False)
    else:
        check("NVIDIA/VRAM", "warn", "GPU NVIDIA não detectada; fallback CPU continua possível", critical=False)

    py_engine = ENGINE / "venv" / "Scripts" / "python.exe"
    py_bridge = BRIDGE / ".venv" / "Scripts" / "python.exe"
    if not py_engine.exists():
        py_engine = ENGINE / "venv" / "bin" / "python"
    if not py_bridge.exists():
        py_bridge = BRIDGE / ".venv" / "bin" / "python"

    check_python_env("Engine imports", py_engine, "import sys; import fastapi; print('python='+sys.version.split()[0]+' fastapi=ok')")
    if py_engine.exists():
        rc, out = run([str(py_engine), "-c", "import torch; print('torch='+torch.__version__+' cuda='+str(torch.cuda.is_available())+' device='+(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'))"], timeout=45)
        check("Engine PyTorch/CUDA", "ok" if rc == 0 else "warn", out[-400:] if out else "sem resposta", critical=False)
    check_python_env("Bridge/voz imports", py_bridge, "import yaml, requests, numpy; import faster_whisper, ctranslate2; print('voice imports ok')")

    for label, path in [
        ("Engine server.py", ENGINE / "server.py"),
        ("Voice server", BRIDGE / "jarvis_voice_server.py"),
        ("Bridge server", BRIDGE / "server.py"),
        ("Supervisor", ROOT / "ARQUIVO_LEGADO" / "BAT_PS1" / "AURA_SUPERVISOR.ps1"),
        ("Installer", ROOT / "AURA_INSTALAR_E_INICIAR_TUDO.bat"),
    ]:
        check(label, "ok" if path.exists() else "fail", str(path), critical=True)

    if py_engine.exists():
        rc, out = run([str(py_engine), "-m", "py_compile", str(ENGINE / "server.py"), str(ENGINE / "orchestrator.py")], timeout=30)
        check("Compilação Engine", "ok" if rc == 0 else "fail", out or "py_compile ok")
    if py_bridge.exists():
        rc, out = run([str(py_bridge), "-m", "py_compile", str(BRIDGE / "server.py"), str(BRIDGE / "jarvis_voice_server.py")], timeout=30)
        check("Compilação Bridge/voz", "ok" if rc == 0 else "fail", out or "py_compile ok")

    ollama = find_ollama()
    if ollama:
        check("Executável Ollama", "ok", ollama)
        rc, out = run([ollama, "list"], timeout=15)
        has_model = (rc == 0 and TARGET_MODEL in out)
        check("Modelo Ollama", "ok" if has_model else "fail", TARGET_MODEL if has_model else f"ausente; saída: {out[-260:]}")
    else:
        check("Executável Ollama", "fail", "não encontrado; instale Ollama ou ajuste o PATH")
        has_model = False

    ollama_status, ollama_body = http("http://127.0.0.1:11434/api/tags")
    check("Ollama API :11434", "ok" if ollama_status in (200, 403) else "fail", f"HTTP {ollama_status}" if ollama_status else ollama_body[-260:])

    service_specs = [
        ("Bridge :8080", 8080, "/health", True),
        ("Engine :8765", 8765, "/health", True),
        ("Voice :8099", 8099, "/api/voice/health", True),
        ("Flask legado :5000", 5000, "/api/health", False),
    ]
    for label, port, path, critical in service_specs:
        status, body = http(f"http://127.0.0.1:{port}{path}")
        if status == 200:
            check(label, "ok", "HTTP 200", critical=critical)
        elif critical:
            check(label, "fail", f"sem resposta: {body[-240:]}", critical=True)
        else:
            check(label, "warn", "offline; endpoint legado opcional", critical=False)

    if args.deep and py_bridge.exists():
        code = "from faster_whisper import WhisperModel; WhisperModel('tiny', device='cuda', compute_type='float16'); print('Whisper CUDA/FP16 OK')"
        rc, out = run([str(py_bridge), "-c", code], timeout=120)
        check("Whisper CUDA profundo", "ok" if rc == 0 else "fail", out[-350:])
    else:
        check("Whisper CUDA profundo", "skip", "use --deep para carregar modelo de teste", critical=False)

    for label, paths in [
        ("Log Engine", [ENGINE / "runtime_engine.log", ENGINE / "engine_server.log", ROOT / "engine_server.log"]),
        ("Log Bridge", [BRIDGE / "runtime_bridge.log", BRIDGE / "bridge_server.log"]),
        ("Log Voice", [BRIDGE / "runtime_voice.log", BRIDGE / "voice_server.log"]),
        ("Log instalador", [ROOT / "install_run.log"]),
    ]:
        check_log(label, paths)

    fails = [r for r in results if r["status"] == "fail" and r.get("critical", True)]
    warns = [r for r in results if r["status"] == "warn"]
    report = {
        "version": "12.6.17",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(ROOT),
        "targetModel": TARGET_MODEL,
        "deep": bool(args.deep),
        "summary": {"pass": sum(r["status"] == "ok" for r in results), "warn": len(warns), "criticalFail": len(fails)},
        "firstCriticalFail": fails[0] if fails else None,
        "results": results,
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["AURA QUANT-X 12.6.17 — RELATÓRIO DE AUDITORIA", "=" * 78]
    lines += [f"[{r['status'].upper():5}] {r['label']}: {r['detail']}" for r in results]
    lines += ["", f"PASS: {report['summary']['pass']}", f"WARN: {report['summary']['warn']}", f"FALHAS CRÍTICAS: {report['summary']['criticalFail']}"]
    lines += ["AÇÃO PRINCIPAL: " + (fails[0]["detail"] if fails else "nenhuma falha crítica detectada")]
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines[-5:]))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
