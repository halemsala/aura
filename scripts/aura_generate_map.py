#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera AURA_MAPA_DO_SISTEMA.md — inventario automatico."""
from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
IGNORE = {"venv", "__pycache__", ".git", "node_modules", ".idea", ".vscode", "dist", "build", "engine/venv"}
PORT_RE = re.compile(r"(?:127\.0\.0\.1|localhost|0\.0\.0\.0)?[:\s](\d{4,5})(?:/|\"|'|\s|$)")
ENV_RE = re.compile(r"os\.getenv\([\"'](\w+)[\"']")
KNOWN_PORTS = {
    "8777": "Hermes Chat API",
    "8765": "Engine AURA",
    "8766": "Matriz",
    "8080": "Bridge",
    "8790": "Tools Control API",
    "8099": "Voice",
    "11434": "Ollama (NUNCA matar)",
}

def scan():
    files, ports, envs = [], {}, set()
    for p in ROOT.rglob("*.py"):
        if any(part in IGNORE for part in p.parts):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        doc = ""
        m = re.search(r'"""(.{0,120}?)"""', src, re.S)
        if m:
            doc = m.group(1).strip().splitlines()[0][:100]
        files.append((rel, len(src), doc))
        for pm in PORT_RE.finditer(src):
            port = pm.group(1)
            try:
                if 1000 < int(port) < 65535:
                    ports.setdefault(port, []).append(rel)
            except ValueError:
                pass
        envs.update(ENV_RE.findall(src))
    return files, ports, sorted(envs)

def main():
    files, ports, envs = scan()
    L = [
        f"# AURA — Mapa do Sistema",
        f"_Gerado em {datetime.now():%Y-%m-%d %H:%M}_",
        "",
        "## Servicos & Portas",
        "",
        "| Porta | Servico | Definido em |",
        "|---|---|---|",
    ]
    for port, where in sorted(ports.items(), key=lambda x: int(x[0])):
        svc = KNOWN_PORTS.get(port, "(desconhecido — catalogar!)")
        L.append(f"| {port} | {svc} | {', '.join(sorted(set(where))[:3])} |")
    L += [
        "",
        "## Inventario .py (amostra top por tamanho)",
        "",
        "| Ficheiro | Bytes | Descricao |",
        "|---|---|---|",
    ]
    for rel, size, doc in sorted(files, key=lambda x: -x[1])[:80]:
        L.append(f"| `{rel}` | {size} | {doc or '—'} |")
    L += ["", f"_Total ficheiros .py indexados: {len(files)}_", "", "## Env vars detectadas", ""]
    L += [f"- `{e}`" for e in envs[:60]]
    L += [
        "",
        "## Fluxo de boot esperado",
        "1. Ollama :11434 (externo)",
        "2. Bridge :8080",
        "3. Engine :8765",
        "4. Matriz :8766",
        "5. Control :8790",
        "6. Hermes Chat :8777",
        "",
        "> Portas sem servico nomeado = candidatas a live_missing no detector.",
        "",
        "## Catalogo de erros",
        "Ver `core/aura_error_catalog.json` + motor `core/aura_error_catalog.py`.",
        "Diagnostico: GET /api/diagnose · Fix: `fix E-NET-004` no chat.",
    ]
    out = ROOT / "AURA_MAPA_DO_SISTEMA.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"OK — {len(files)} files, {len(ports)} ports → {out}")

if __name__ == "__main__":
    main()
