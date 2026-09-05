#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera dataset Alpaca para fine-tune do Hermes a partir do catalogo (+ memoria se existir)."""
from __future__ import annotations
import json, random, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "core" / "aura_error_catalog.json"
OUT = ROOT / "training" / "hermes_dataset.json"

QUESTION_TEMPLATES = [
    "o {svc} caiu", "o {svc} ta off", "{svc} offline", "por que o {svc} nao ta a dar",
    "o {svc} quebrou de novo", "erro no {svc}", "arruma o {svc}", "conserta o {svc}",
    "o que aconteceu com o {svc}?", "{svc} nao responde", "{svc} nao carrega",
    "tem erro no sistema", "diagnostica tudo", "o que ta errado?", "status ta estranho",
    "failed to fetch de novo", "deu 500", "deu 404",
]

def ideal_answer(entry: dict) -> str:
    loc = entry.get("location", {}) or {}
    onde = loc.get("file") or loc.get("service") or "?"
    porta = f" (porta {loc.get('port')})" if loc.get("port") else ""
    fix = (entry.get("fix") or {}).get("action", "")
    return (
        f"{entry['code']} · {entry['title']}\n"
        f"Onde: {onde}{porta}\n"
        f"Causa: {entry.get('cause', '')}\n"
        f"Corrigir: \"{fix}\" (ou envie: fix {entry['code']})"
    )

def build_synthetic() -> list:
    if not CATALOG.exists():
        return []
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    pairs = []
    for e in data.get("entries", []):
        svc = (e.get("location") or {}).get("service") or "sistema"
        for tmpl in QUESTION_TEMPLATES:
            pairs.append({"instruction": tmpl.format(svc=svc), "input": "", "output": ideal_answer(e)})
    smalltalk = [
        ("qual seu nome?", "Sou o Hermes, operador do AURA. Posso diagnosticar, corrigir e reiniciar servicos. Tenta: status, corrige ou diagnostico."),
        ("quem e voce", "Hermes — operador tecnico do AURA, paper-trade ativo."),
        ("o que voce faz?", "Diagnostico erros com codigos do catalogo, corrijo e reinicio servicos (exceto Ollama). Pede: status ou diagnostico."),
        ("obrigado", "A ordem. Se algo cair, manda diagnostico que eu aponto o erro com codigo."),
    ]
    pairs += [{"instruction": q, "input": "", "output": a} for q, a in smalltalk]
    return pairs

def build_from_memory() -> list:
    pairs = []
    candidates = [
        ROOT / "hermes_v10" / "data" / "lcm_memory.db",
        ROOT / "data" / "lcm_memory.db",
        ROOT / "hermes_v10" / "orchestrator" / "state_checkpoints" / "memory.db",
    ]
    for db in candidates:
        if not db.exists():
            continue
        try:
            con = sqlite3.connect(str(db))
            # schema-agnostic: try common shapes
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            for table in tables:
                cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
                colset = {c.lower() for c in cols}
                if not ({"role", "content"} <= colset or {"role", "text"} <= colset):
                    continue
                content_col = "content" if "content" in colset else "text"
                role_col = "role"
                rows = con.execute(f"SELECT {role_col}, {content_col} FROM {table} LIMIT 2000").fetchall()
                for i, (role, content) in enumerate(rows):
                    if str(role).lower() in ("user", "human") and i + 1 < len(rows):
                        r2, c2 = rows[i + 1]
                        if str(r2).lower() in ("assistant", "ai", "bot"):
                            pairs.append({
                                "instruction": str(content)[:1500],
                                "input": "",
                                "output": str(c2)[:2000],
                            })
            con.close()
        except Exception:
            continue
    return pairs

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_synthetic() + build_from_memory()
    random.shuffle(dataset)
    OUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(dataset)} exemplos → {OUT}")

if __name__ == "__main__":
    main()
