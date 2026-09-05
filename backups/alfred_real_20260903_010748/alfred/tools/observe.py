"""Observar PC e Aura: processos, janela em foco, portas, GPU, captura opcional."""
import os
import subprocess
from pathlib import Path

from .. import flags, paths
from ..config import get_config
from ..registry import ToolSpec, register
from . import capture, system_tools


def _v0(args) -> dict:
    return {}


def _foreground_title() -> str:
    if os.name != "nt":
        return ""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value[:200]
    except Exception:  # noqa: BLE001
        return ""


def _top_processes(n: int = 12) -> list:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                procs.append(info)
            except (psutil.Error, TypeError):
                continue
        procs.sort(key=lambda x: float(x.get("cpu_percent") or 0), reverse=True)
        return procs[:n]
    except ImportError:
        try:
            out = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"], text=True, timeout=8, errors="replace")
            rows = []
            for line in out.splitlines()[:n]:
                parts = [x.strip('"') for x in line.split(",")]
                if parts:
                    rows.append({"name": parts[0]})
            return rows
        except Exception:
            return []


def observe_pc(args, ctx) -> dict:
    fl = flags.load_flags()
    if not fl.get("observe_pc_enabled", True):
        return {"blocked": True, "nota": "observação desligada nas flags"}
    st = system_tools.system_status({}, ctx)
    shot = None
    if (args or {}).get("screenshot"):
        shot = capture.capture_screen({"cleanup": True}, ctx)
    return {
        "foreground_window": _foreground_title(),
        "top_processes": _top_processes(),
        "gpu": st.get("gpu"),
        "cpu_percent": st.get("cpu_percent"),
        "ram_used_pct": st.get("ram_used_pct"),
        "ollama": st.get("ollama"),
        "screenshot": shot,
        "nota": "sem keylogger, sem leitura de outros ecrãs além do título da janela e captura se pedida",
    }


register(ToolSpec("observe_pc", observe_pc, _v0, risk="low", mutating=False,
                  summary="Vê o que se passa no PC: janela em foco, processos, GPU, Aura"))


def observe_aura(args, ctx) -> dict:
    from .control import services_status
    fl = flags.load_flags()
    svc = services_status({}, ctx)
    return {
        "flags": fl,
        "services": svc,
        "focus": __import__("alfred.focus_mode", fromlist=["status"]).status(),
        "gpu_share": __import__("alfred.gpu_share.manager", fromlist=["list_workers"]).list_workers(),
    }


register(ToolSpec("observe_aura", observe_aura, _v0, risk="low", mutating=False,
                  summary="Estado completo do Aura: flags, serviços, foco, workers GPU"))
