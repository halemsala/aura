#!/usr/bin/env python3
# Force hermes_v10/core onto sys.path before chat API import.
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AURA_ROOT") or HERE.parent)
CAND = [
    HERE,
    HERE / "core",
    ROOT / "hermes_v10",
    ROOT,
    Path(r"C:\aura") / "hermes_v10",
    Path(r"C:\AURA_V25") / "hermes_v10",
]
for p in CAND:
    if p and p.exists():
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
pkg = None
for p in CAND:
    if p and (p / "core" / "hermes_llm_engine.py").is_file():
        pkg = p
        break
if pkg is None:
    sys.stderr.write("FATAL: core/hermes_llm_engine.py nao encontrado. Copia a pasta hermes_v10 COMPLETA (com core\\).\n")
    sys.stderr.write("AURA_ROOT=%s\n" % ROOT)
    sys.exit(2)
os.environ["AURA_ROOT"] = str(ROOT)
os.chdir(str(pkg))
if str(pkg) not in sys.path:
    sys.path.insert(0, str(pkg))
api = pkg / "scripts" / "hermes_v10_chat_api.py"
if not api.is_file():
    sys.stderr.write("FATAL: %s ausente\n" % api)
    sys.exit(2)
import runpy
runpy.run_path(str(api), run_name="__main__")
