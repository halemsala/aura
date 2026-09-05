#!/usr/bin/env python3
"""Torna o import do knowledge_review_gate não-fatal em engine/server.py."""
from __future__ import annotations

from pathlib import Path

OLD = """try:
    from knowledge_review_gate import router as knowledge_router
except ImportError:
    from engine.knowledge_review_gate import router as knowledge_router
app.include_router(knowledge_router)
"""

NEW = """try:
    from knowledge_review_gate import router as knowledge_router
except ImportError:
    try:
        from engine.knowledge_review_gate import router as knowledge_router
    except ImportError:
        knowledge_router = None
if knowledge_router is not None:
    app.include_router(knowledge_router)
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    server = root / "engine" / "server.py"
    if not server.is_file():
        print("SKIP server.py ausente")
        return 0
    text = server.read_text(encoding="utf-8", errors="replace")
    if "if knowledge_router is not None:" in text:
        print("OK server.py ja resiliente")
        return 0
    if OLD not in text:
        print("AVISO bloco original nao encontrado; knowledge_review_gate.py ainda e necessario")
        return 0
    server.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print("OK server.py patch knowledge import")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
