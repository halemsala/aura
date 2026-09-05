#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remendo C:\\aura\\engine\\server.py — alias fixtureId + /api/telemetry não rebenta 500."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\aura")
SRC = ROOT / "engine" / "server.py"


def main() -> int:
    if not SRC.exists():
        print("FALHA: não achei", SRC)
        return 1
    text = SRC.read_text(encoding="utf-8")
    bak = SRC.with_suffix(SRC.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(SRC, bak)
    print("backup:", bak)

    if "AliasChoices" not in text:
        text = text.replace(
            "from pydantic import BaseModel, Field",
            "from pydantic import AliasChoices, BaseModel, Field",
            1,
        )
        if "AliasChoices" not in text:
            text = text.replace(
                "from pydantic import BaseModel",
                "from pydantic import AliasChoices, BaseModel",
                1,
            )

    old = """class TelemetryPayload(BaseModel):
    match_id: str
"""
    new = """class TelemetryPayload(BaseModel):
    match_id: str = Field(validation_alias=AliasChoices("match_id", "fixtureId", "fixture_id"))
"""
    if old in text:
        text = text.replace(old, new, 1)
        print("alias fixtureId OK")
    elif "AliasChoices(\"match_id\"" in text or "AliasChoices('match_id'" in text:
        print("alias já existia")
    else:
        print("AVISO: bloco TelemetryPayload não encontrado tal como esperado")

    needle = "@app.post(\"/api/telemetry\")\nasync def post_telemetry(payload: TelemetryPayload):"
    wrap = '''@app.post("/api/telemetry")
async def post_telemetry(payload: TelemetryPayload):
    try:
        return await _post_telemetry_inner(payload)
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger("aura.engine_server").exception("telemetry 500 capturado: %s", exc)
        return {"ok": False, "accepted": False, "error": str(exc)[:240], "paper_trade": True, "execution_allowed": False}

async def _post_telemetry_inner(payload: TelemetryPayload):'''
    if "_post_telemetry_inner" not in text:
        if needle in text:
            text = text.replace(needle, wrap, 1)
            print("wrapper 500 OK")
        else:
            print("AVISO: decorator /api/telemetry não encontrado")
    else:
        print("wrapper já existia")

    SRC.write_text(text, encoding="utf-8")
    print("escrito", SRC)
    print("Reinicia só o Engine e testa o POST de novo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
