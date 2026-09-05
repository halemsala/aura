#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Domain Lock V28
Garante que o LLM do Hermes só fale de futebol / escanteios / SokkerPRO.
Bloqueia respostas de bolsa, ações, tickers, etc.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FOOTBALL_SYSTEM = """# SYSTEM PROMPT OBRIGATÓRIO — AURA / HERMES
Você é o Hermes do sistema AURA QUANT-X.
Domínio ÚNICO e EXCLUSIVO: futebol ao vivo, escanteios (corners), estatísticas de partida, SokkerPRO, paper-trade de corners.

PROIBIDO ABSOLUTAMENTE:
- Falar de ações, bolsa de valores, tickers, IBOVESPA, NASDAQ, Vale, Itaú, Gerdau, Embraer, dividendos, carteira de investimentos.
- Inventar placar, odd, fixture ou evento que não esteja no snapshot fornecido.
- Sugerir execução real de aposta (execution_allowed=false).
- Sair do domínio futebol/corners.

Se a pergunta não for sobre futebol/escanteios/SokkerPRO/AURA, responda exatamente:
"Fora de domínio. Este sistema trata apenas de futebol ao vivo e escanteios (paper-trade)."

Invariantes: paper_trade=true · execution_allowed=false · GLM_ADVISORY_ONLY=true
Fonte de verdade: snapshot do Bridge + DOM SokkerPRO + /api/ui/state.
Nunca complete lacunas por inferência.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    prompts = root / "engine" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    target = prompts / "system_hermes_football_only.txt"
    if args.apply or not target.exists():
        target.write_text(FOOTBALL_SYSTEM, encoding="utf-8")
        print(f"[OK] Domain lock escrito em: {target}")
    else:
        print(f"[SKIP] Já existe: {target}")

    # Também grava um marker para o supervisor
    marker = root / "engine" / "data" / "hermes_domain_lock.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        '{"domain":"football_corners","version":"V28","forbidden":["stocks","bolsa","ações"]}',
        encoding="utf-8",
    )
    print(f"[OK] Marker: {marker}")
    print("Invariantes mantidos: paper_trade=true | execution_allowed=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
