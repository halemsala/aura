#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HERMES CONTROL PANEL V9 — grafo + score + postmortem."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

ROOT_CANDIDATES = [
    Path(os.environ.get("AURA_ROOT", "")),
    Path(r"C:\aura"),
    Path(r"C:\AURA_V25"),
    Path.cwd(),
    Path(__file__).resolve().parents[1],
]


def find_root(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if (p / "engine" / "server.py").exists():
            return p.resolve()
    for c in ROOT_CANDIDATES:
        if c and (c / "engine" / "server.py").exists():
            return c.resolve()
    return Path.cwd().resolve()


def find_hermes_script(root: Path) -> Path | None:
    for p in [
        root / "scripts" / "hermes_autonomous_os.py",
        Path(__file__).resolve().parent / "hermes_autonomous_os.py",
    ]:
        if p.exists():
            return p
    return None


def find_python(root: Path) -> str:
    venv = root / "engine" / "venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


class HermesPanel(tk.Tk):
    def __init__(self, root: Path):
        super().__init__()
        self.aura_root = root
        self.hermes_script = find_hermes_script(root)
        self.py = find_python(root)
        self.running = False
        self.stop_flag = False
        self.cycle = 0
        self.max_cycles = 25
        self.use_llm = tk.BooleanVar(value=True)
        self.log_queue: queue.Queue = queue.Queue()

        self.title("HERMES V9 — Planner + Auditor Panel")
        self.geometry("1000x740")
        self.minsize(840, 580)
        self.configure(bg="#0d1117")

        hdr = tk.Frame(self, bg="#010409", height=60)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        tk.Label(
            hdr, text="⚙  HERMES V9  ·  INCIDENT + RAG + NO-FLAP",
            font=("Segoe UI", 15, "bold"), fg="#58a6ff", bg="#010409",
        ).pack(side=tk.LEFT, padx=14, pady=12)
        self.status_badge = tk.Label(
            hdr, text=" PRONTO ", font=("Segoe UI", 11, "bold"),
            fg="#0d1117", bg="#3fb950", padx=10, pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT, padx=14)

        info = tk.Frame(self, bg="#161b22", height=40)
        info.pack(fill=tk.X)
        info.pack_propagate(False)
        self.root_lbl = tk.Label(
            info, text=f"ROOT: {self.aura_root}", font=("Consolas", 9),
            fg="#8b949e", bg="#161b22", anchor="w",
        )
        self.root_lbl.pack(side=tk.LEFT, padx=12)
        self.intel_lbl = tk.Label(
            info, text="Score:—  Mem:0  LLM:off", font=("Consolas", 9),
            fg="#a371f7", bg="#161b22",
        )
        self.intel_lbl.pack(side=tk.RIGHT, padx=12)
        self.progress_lbl = tk.Label(
            info, text="Ciclo 0 / 25", font=("Consolas", 9, "bold"),
            fg="#58a6ff", bg="#161b22",
        )
        self.progress_lbl.pack(side=tk.RIGHT, padx=16)

        roles = tk.Frame(self, bg="#0d1117")
        roles.pack(fill=tk.X, padx=12, pady=(8, 0))
        tk.Label(roles, text="GRAFO  DETECT→DIAGNOSE→ACT→VERIFY→LEARN→ROUTE",
                 font=("Segoe UI", 8, "bold"), fg="#8b949e", bg="#0d1117").pack(anchor="w")
        self.role_vars = {}
        row = tk.Frame(roles, bg="#0d1117")
        row.pack(fill=tk.X, pady=3)
        for name in ("SCANNER", "KNOWLEDGE", "FIXER", "VALIDATOR", "SENTINEL", "LLM"):
            f = tk.Frame(row, bg="#21262d", padx=8, pady=3)
            f.pack(side=tk.LEFT, padx=3)
            lbl = tk.Label(f, text=name, font=("Consolas", 8), fg="#8b949e", bg="#21262d")
            lbl.pack()
            self.role_vars[name] = lbl

        sec = tk.Frame(self, bg="#0d1117")
        sec.pack(fill=tk.X, padx=12, pady=(6, 0))
        self.sector_vars = {}
        row2 = tk.Frame(sec, bg="#0d1117")
        row2.pack(fill=tk.X, pady=3)
        for s in ("codigo", "conexao", "servicos", "captura", "seguranca", "ollama"):
            f = tk.Frame(row2, bg="#21262d", padx=6, pady=2)
            f.pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(f, text=s.upper(), font=("Consolas", 8), fg="#8b949e", bg="#21262d")
            lbl.pack()
            self.sector_vars[s] = lbl
        self.sector_detail = tk.Label(
            sec, text="Aguardando comando...", font=("Consolas", 9),
            fg="#c9d1d9", bg="#0d1117", anchor="w",
        )
        self.sector_detail.pack(fill=tk.X, pady=(2, 4))

        self.pbar = ttk.Progressbar(self, mode="determinate", maximum=self.max_cycles)
        self.pbar.pack(fill=tk.X, padx=12, pady=4)

        log_frame = tk.Frame(self, bg="#0d1117")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
        tk.Label(log_frame, text="LOG  ·  fonte de verdade = ui/state + DOM, nunca o parágrafo do GLM",
                 font=("Segoe UI", 8, "bold"), fg="#8b949e", bg="#0d1117").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 9), bg="#010409", fg="#c9d1d9",
            insertbackground="#c9d1d9", relief=tk.FLAT, wrap=tk.WORD, height=16,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        for tag, color in [("ok", "#3fb950"), ("warn", "#d29922"), ("err", "#f85149"),
                           ("info", "#58a6ff"), ("fixed", "#a371f7"), ("mem", "#db61a2")]:
            self.log.tag_config(tag, foreground=color)

        btn = tk.Frame(self, bg="#0d1117")
        btn.pack(fill=tk.X, padx=12, pady=8)
        self.btn_run = tk.Button(
            btn, text="▶  CORRIGIR ATÉ FUNCIONAR (V9)",
            font=("Segoe UI", 11, "bold"), bg="#238636", fg="white",
            activebackground="#2ea043", relief=tk.FLAT, padx=14, pady=7,
            cursor="hand2", command=self.start_auto,
        )
        self.btn_run.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_once = tk.Button(
            btn, text="1 CICLO", font=("Segoe UI", 10), bg="#21262d", fg="#c9d1d9",
            relief=tk.FLAT, padx=10, pady=7, command=self.run_once,
        )
        self.btn_once.pack(side=tk.LEFT, padx=3)
        self.btn_stop = tk.Button(
            btn, text="■ PARAR", font=("Segoe UI", 10), bg="#da3633", fg="white",
            relief=tk.FLAT, padx=10, pady=7, state=tk.DISABLED, command=self.stop,
        )
        self.btn_stop.pack(side=tk.LEFT, padx=3)
        tk.Checkbutton(
            btn, text="Usar LLM (Ollama)", variable=self.use_llm,
            font=("Segoe UI", 9), fg="#c9d1d9", bg="#0d1117",
            activebackground="#0d1117", selectcolor="#21262d",
            activeforeground="#c9d1d9",
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn, text="Postmortem", font=("Segoe UI", 9), bg="#21262d", fg="#8b949e",
            relief=tk.FLAT, padx=8, pady=5, command=self.run_postmortem,
        ).pack(side=tk.RIGHT, padx=4)
        tk.Button(
            btn, text="Relatório", font=("Segoe UI", 9), bg="#21262d", fg="#8b949e",
            relief=tk.FLAT, padx=8, pady=5, command=self.open_report,
        ).pack(side=tk.RIGHT)

        tk.Label(
            self, text="paper_trade=true  ·  execution_allowed=false  ·  V9 planner  ·  stale>45s  ·  lock",
            font=("Consolas", 8), fg="#484f58", bg="#0d1117",
        ).pack(pady=(0, 6))

        if not self.hermes_script:
            self._log("[ERRO] hermes_autonomous_os.py não encontrado", "err")
            self.btn_run.config(state=tk.DISABLED)
            self.btn_once.config(state=tk.DISABLED)
        else:
            self._log(f"Script: {self.hermes_script}", "info")
            self._log(f"Python: {self.py}", "info")
            self._log("Pronto. Clique em CORRIGIR ATÉ FUNCIONAR.", "ok")
        self.after(180, self._poll_queue)

    def _log(self, msg: str, tag: str = "") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((f"[{ts}] {msg}\n", tag))

    def _poll_queue(self) -> None:
        try:
            while True:
                line, tag = self.log_queue.get_nowait()
                self.log.insert(tk.END, line, tag if tag else ())
                self.log.see(tk.END)
        except queue.Empty:
            pass
        self.after(140, self._poll_queue)

    def _set_status(self, text: str, color: str) -> None:
        self.status_badge.config(text=f" {text} ", bg=color)

    def _set_role(self, name: str, active: bool) -> None:
        lbl = self.role_vars.get(name)
        if lbl:
            lbl.config(fg="#3fb950" if active else "#8b949e")

    def _set_sector(self, name: str, state: str) -> None:
        lbl = self.sector_vars.get(name)
        if not lbl:
            return
        colors = {"OK": "#3fb950", "FAIL": "#f85149", "FIX": "#a371f7", "RUN": "#58a6ff"}
        lbl.config(fg=colors.get(state, "#8b949e"))

    def _run_hermes(self, extra: list) -> tuple[int, str]:
        if not self.hermes_script:
            return 1, "script ausente"
        cmd = [self.py, str(self.hermes_script), "--root", str(self.aura_root)] + extra
        if self.use_llm.get():
            cmd.append("--llm")
        env = os.environ.copy()
        env["PAPER_TRADE"] = "true"
        env["EXECUTION_ALLOWED"] = "false"
        env["AURA_ROOT"] = str(self.aura_root)
        env["PYTHONUTF8"] = "1"
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, timeout=220, cwd=str(self.aura_root),
            )
            return r.returncode, (r.stdout or "") + "\n" + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return 1, "TIMEOUT 220s"
        except Exception as e:
            return 1, str(e)

    def start_auto(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_flag = False
        self.btn_run.config(state=tk.DISABLED)
        self.btn_once.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self._set_status("A CORRIGIR", "#d29922")
        threading.Thread(target=self._auto_loop, daemon=True).start()

    def run_once(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_flag = False
        self.btn_run.config(state=tk.DISABLED)
        self.btn_once.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        threading.Thread(target=self._once, daemon=True).start()

    def stop(self) -> None:
        self.stop_flag = True
        self._log("Paragem pedida...", "warn")

    def open_report(self) -> None:
        p = self.aura_root / "logs_supervisor" / "HERMES_AUTONOMOUS_LATEST.txt"
        if p.exists() and sys.platform == "win32":
            os.startfile(str(p))  # type: ignore
        elif p.exists():
            self._log(str(p), "info")
        else:
            messagebox.showinfo("Relatório", "Ainda não existe HERMES_AUTONOMOUS_LATEST.txt")

    def run_postmortem(self) -> None:
        script = self.aura_root / "scripts" / "hermes_postmortem.py"
        if not script.exists():
            script = Path(__file__).resolve().parent / "hermes_postmortem.py"
        if not script.exists():
            messagebox.showinfo("Postmortem", "script ausente")
            return
        subprocess.Popen([self.py, str(script), "--root", str(self.aura_root)])
        self._log("Postmortem lançado", "info")

    def _parse_intel(self, out: str) -> None:
        mem, llm, score = "0", "off", "—"
        for line in out.splitlines():
            if "MemoryHits:" in line:
                parts = line.replace(":", " ").split()
                for p in parts:
                    if p.isdigit():
                        mem = p
                        break
            if "LLM:" in line and ("True" in line or "true" in line):
                llm = "on"
            if "HEALTH_SCORE=" in line:
                m = [t.split("=")[-1] for t in line.split() if "HEALTH_SCORE=" in t]
                if m:
                    score = m[0]
            if "score=" in line and score == "—":
                for t in line.split():
                    if t.startswith("score="):
                        score = t.split("=")[-1]
        self.intel_lbl.config(text=f"Score:{score}  Mem:{mem}  LLM:{llm}")

    def _emit_out(self, out: str) -> str:
        status_line = "DEGRADED"
        for line in out.splitlines():
            low = line.lower()
            tag = ""
            if "Status:" in line:
                status_line = line.strip()
            if "memory hit" in low:
                tag, _ = "mem", self._set_role("KNOWLEDGE", True)
            elif "fixed" in low:
                tag = "fixed"
            elif "critical" in low or "syntax" in low:
                tag = "err"
            elif "healthy" in low:
                tag = "ok"
            elif "llm" in low:
                tag = "info"
                self._set_role("LLM", True)
            elif "circuit" in low:
                tag = "warn"
                self._set_role("SENTINEL", True)
            for s in self.sector_vars:
                if s in low:
                    if "ok" in low or "healthy" in low:
                        self._set_sector(s, "OK")
                    elif any(x in low for x in ("fail", "critical", "off", "down", "stale")):
                        self._set_sector(s, "FAIL")
            if any(k in line for k in (
                "FIXED", "CRITICAL", "SYNTAX", "ENGINE", "BRIDGE", "CAPTURA",
                "Status", "MEMORY", "LLM", "VERIFY", "PORT_", "VENV", "OLLAMA",
                "HEALTH", "STALE", "GROUNDING", "CIRCUIT", "CANARY",
            )) and line.strip():
                self._log(line.strip()[:140], tag)
        return status_line

    def _finish(self, status: str) -> None:
        color = "#3fb950" if status == "HEALTHY" else "#d29922"
        self._set_status(status, color)
        self.sector_detail.config(text=f"Terminado: {status}")
        self.running = False
        self.btn_run.config(state=tk.NORMAL)
        self.btn_once.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def _once(self) -> None:
        self._log("CICLO ÚNICO V9", "info")
        self._set_role("SCANNER", True)
        rc, out = self._run_hermes(["--once", "--fix"])
        self._parse_intel(out)
        status_line = self._emit_out(out)
        status = "HEALTHY" if rc == 0 or "HEALTHY" in status_line.upper() else "DEGRADED"
        self._finish(status)

    def _auto_loop(self) -> None:
        self._log("MODO AUTOMÁTICO V9 — closed-loop", "info")
        healthy_streak = 0
        for i in range(1, self.max_cycles + 1):
            if self.stop_flag:
                self._log("Parado pelo utilizador.", "warn")
                break
            self.cycle = i
            self.progress_lbl.config(text=f"Ciclo {i} / {self.max_cycles}")
            self.pbar["value"] = i
            self.sector_detail.config(text=f"Ciclo {i}: DETECT→…→ROUTE")
            self._log(f">>> CICLO {i}/{self.max_cycles}", "info")
            rc, out = self._run_hermes(["--once", "--fix"])
            self._parse_intel(out)
            status_line = self._emit_out(out)
            if rc == 0 or "HEALTHY" in status_line.upper():
                healthy_streak += 1
                self._set_status("HEALTHY", "#3fb950")
                if healthy_streak >= 2:
                    self._log("*** 2× HEALTHY — V9 concluiu ***", "ok")
                    break
            else:
                healthy_streak = 0
                self._set_status("A CORRIGIR", "#d29922")
                if "CIRCUIT" in out.upper() and "OPEN" in out.upper():
                    self._log("Circuit breaker — a parar", "err")
                    break
                time.sleep(7)
        else:
            self._log(f"Limite de {self.max_cycles} ciclos.", "warn")
        self._finish("AUTO")


def main() -> int:
    root_arg = None
    if "--root" in sys.argv:
        i = sys.argv.index("--root")
        if i + 1 < len(sys.argv):
            root_arg = sys.argv[i + 1]
    HermesPanel(find_root(root_arg)).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
