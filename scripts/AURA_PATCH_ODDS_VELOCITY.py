#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C:\\aura\\engine\\server.py — não rebentar em analysis['odds_velocity']."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

SRC = Path(r"C:\aura\engine\server.py")


def main() -> int:
    if not SRC.exists():
        print("FALHA", SRC)
        return 1
    text = SRC.read_text(encoding="utf-8")
    bak = SRC.with_suffix(SRC.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(SRC, bak)
    print("backup:", bak)

    a = "analysis = _run_snapshot_analysis(snapshot, payload.match_id)\n    estado = analysis[\"decision\"]\n    velocity = analysis[\"odds_velocity\"]"
    b = (
        "analysis = _run_snapshot_analysis(snapshot, payload.match_id) or {}\n"
        "    if not isinstance(analysis, dict):\n"
        "        analysis = {}\n"
        "    estado = analysis.get(\"decision\") or \"HOLD\"\n"
        "    velocity = float(analysis.get(\"odds_velocity\") or 0.0)\n"
        "    analysis[\"decision\"] = estado\n"
        "    analysis[\"odds_velocity\"] = velocity"
    )
    if a in text:
        text = text.replace(a, b, 1)
        print("odds_velocity guard OK")
    elif "analysis.get(\"odds_velocity\")" in text:
        print("guard já existia")
    else:
        print("AVISO: bloco exacto não encontrado — não alterei analysis")

    SRC.write_text(text, encoding="utf-8")
    print("escrito", SRC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
