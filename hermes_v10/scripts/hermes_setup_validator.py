#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validador de ambiente Hermes V10."""
from __future__ import annotations
import argparse, json, os, shutil, socket, sys
from pathlib import Path

def port_free_or_up(port: int) -> str:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return "IN_USE"
    except OSError:
        return "FREE"

def main(root: str) -> int:
    root_p = Path(root).resolve()
    print(f"=== HERMES V10 SETUP VALIDATOR ===\nROOT={root_p}")
    ok = True
    py = shutil.which("python") or shutil.which("py")
    print(f"[{'OK' if py else 'FAIL'}] python={py}")
    if not py:
        ok = False
    for d in ("scripts", "engine", "logs_supervisor", "bridge"):
        p = root_p / d
        exists = p.exists()
        print(f"[{'OK' if exists else 'WARN'}] dir {d}")
    for f in (
        "scripts/hermes_v10_chat_api.py",
        "scripts/hermes_v9_chat_api.py",
        "engine/agents/hermes_agents_v9_max.py",
        "hermes_config.json",
    ):
        # check root or package-local
        exists = (root_p / f).exists() or (Path(__file__).resolve().parents[1] / f).exists()
        print(f"[{'OK' if exists else 'WARN'}] file {f}")
    for port in (8777, 8080, 8765, 8766):
        print(f"[INFO] port {port}: {port_free_or_up(port)}")
    print(f"PAPER_TRADE={os.environ.get('PAPER_TRADE', 'unset')}")
    print(f"EXECUTION_ALLOWED={os.environ.get('EXECUTION_ALLOWED', 'unset')}")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    sys.exit(main(ap.parse_args().root))
