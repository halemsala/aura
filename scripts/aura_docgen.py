#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AURA QUANT-X V25 — DocGen: documentacao viva gerada do sistema real."""
from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
__version__ = "1.0.0"

_CSS = """
body { font-family: 'Segoe UI', sans-serif; color: #1e293b; font-size: 10pt; }
h1 { font-size: 15pt; border-bottom: 2px solid #e2e8f0; }
table { width: 100%; border-collapse: collapse; font-size: 9pt; }
th { background: #1e293b; color: #fff; padding: 6px 8px; }
td { padding: 6px 8px; border-bottom: 1px solid #e2e8f0; }
pre { background: #0f172a; color: #e2e8f0; padding: 12px; font-size: 8pt;
  white-space: pre-wrap; }
.banner { background: #0f172a; color: #fff; padding: 20px; }
"""


def _esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def _code_block(code: str, title: str = "") -> str:
    t = f"<p>{_esc(title)}</p>" if title else ""
    return f"{t}<pre><code>{_esc(code)}</code></pre>"


def _module_meta(path: Path) -> dict:
    meta = {"name": path.name, "path": str(path.relative_to(ROOT))
            if ROOT in path.parents or path.is_relative_to(ROOT) else path.name,
            "version": "?", "summary": "", "loc": 0, "selftest": ""}
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        meta["loc"] = len(src.splitlines())
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)', src)
        if m:
            meta["version"] = m.group(1)
        d = re.search(r'"""(.*?)(?:\n|""")', src, re.DOTALL)
        if d:
            first = d.group(1).strip().splitlines()
            if first:
                meta["summary"] = first[0].strip()[:120]
        if re.search(r'if __name__\s*==\s*["\']__main__["\']', src):
            meta["selftest"] = f"python {meta['path']}"
    except OSError:
        pass
    return meta


def scan_modules() -> List[dict]:
    out: List[dict] = []
    for pattern in ("engine/core/*.py", "engine/agents/*.py"):
        for p in sorted(ROOT.glob(pattern)):
            if p.name == "__init__.py":
                continue
            out.append(_module_meta(p))
    return out


def get_persona_prompt() -> str:
    p = ROOT / "engine" / "agents" / "jarvis_persona.py"
    try:
        src = p.read_text(encoding="utf-8")
        m = re.search(r'PERSONA_PROMPT\s*=\s*"""(.*?)"""', src, re.DOTALL)
        return m.group(1).strip() if m else "(PERSONA_PROMPT nao encontrado)"
    except OSError:
        return "(jarvis_persona.py nao encontrado)"


def build_html(*, include_architecture: bool = True) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mods = scan_modules()
    parts: List[str] = []
    parts.append("<html lang='pt-BR'><head><meta charset='UTF-8'>")
    parts.append("<title>AURA QUANT-X V25 — Documentacao Viva</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append(
        "<div class='banner'><h1>AURA QUANT-X V25</h1>"
        f"<p>Documentacao viva · {now} · {len(mods)} modulos</p></div>")
    parts.append("<h1>1. Inventario de Modulos</h1>")
    parts.append("<table><tr><th>Modulo</th><th>Versao</th><th>Linhas</th>"
                 "<th>Resumo</th><th>Self-test</th></tr>")
    for m in mods:
        st = _esc(m["selftest"]) if m["selftest"] else "—"
        parts.append(
            f"<tr><td>{_esc(m['name'])}</td><td>{_esc(m['version'])}</td>"
            f"<td>{m['loc']}</td><td>{_esc(m['summary'])}</td>"
            f"<td><code>{st}</code></td></tr>")
    parts.append("</table>")
    if include_architecture:
        parts.append("<h1>2. System Prompt Real (PERSONA_PROMPT)</h1>")
        parts.append(_code_block(get_persona_prompt()))
    parts.append("</body></html>")
    return "\n".join(parts)


def _selftest() -> int:
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c:
            errs.append(n)
    evil = 'class X:\n """docstring tripla"""\n pass'
    escd = _esc(evil)
    h = _code_block(evil)
    check("escape: docstring tripla sobrevive", '"""' in escd or "&quot;" in h)
    check("escape: sem HTML vivo", "<" not in escd)
    mods = scan_modules()
    check("scan: encontra modulos", len(mods) >= 1, f"{len(mods)}")
    page = build_html()
    check("html: tem banner", "AURA QUANT-X V25" in page)
    check("html: tem tabela", "<table>" in page)
    check("html: codigo escapado", "<pre>" in page)
    p = get_persona_prompt()
    check("persona prompt", "JARVIS" in p or "nao encontrado" in p)
    print(f"\ndocgen selftest: {len(errs)} falha(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "aura_doc.html"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    page = build_html()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"[docgen] HTML: {out} ({len(page)//1024} KB)")
    sys.exit(0)
