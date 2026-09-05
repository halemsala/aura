#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Knowledge Index V7 — RAG leve + ingestão de runbooks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

AURA_KB: List[Dict[str, str]] = [
    {
        "id": "code_drift",
        "tags": "code drift grounding features fixture_context snapshot_for_engine audit",
        "title": "Deriva vs baseline CLEAN",
        "body": "Falta padrão CLEAN em grounding/features/server. Não auto-patchar ficheiro grande sem evidência.",
        "action": "Comparar com AURA 12.7 CLEAN; não reinstalar à cegas",
    },
    {
        "id": "zombie_port",
        "tags": "zombie porta health recycle_port safe_start",
        "title": "Porta zombie",
        "body": "LISTEN sem HTTP 200. recycle_port allowlist 8080/8765/8099 e depois safe_start.",
        "action": "recycle_port + safe_start",
    },

    {
        "id": "try_nest",
        "tags": "syntax try except deep_diagnostic matrix_full_diagnostic import",
        "title": "Try aninhado quebrado",
        "body": "Dois try seguidos sem except. Separar blocos try/except.",
        "action": "KNOWN_SYNTAX_FIXES deep_diagnostic_try_nest",
    },
    {
        "id": "fixture_context",
        "tags": "chat sem dados view fixture_context server grounding",
        "title": "Chat sem dados com view cheio",
        "body": "_fixture_context no server.py não lia view. Lift view/payload.",
        "action": "Verificar engine/server.py e engine/grounding.py",
    },
    {
        "id": "dangerous_home",
        "tags": "dangerous home missing features quality gate lista dict",
        "title": "dangerous.home MISSING",
        "body": "Gate só aceitava dict; view pode ser lista [h,a].",
        "action": "engine/features.py + engine_core.py",
    },
    {
        "id": "captura_stale",
        "tags": "captura live_latest empty feed sokkerpro extensao stale 45",
        "title": "Captura vazia ou stale",
        "body": "live_latest vazio ou >45s. SokkerPRO live + extensão + aba activa. Não reinstalar.",
        "action": "SokkerPRO + extensão + F5",
    },
    {
        "id": "ports_down",
        "tags": "porta off bridge engine voice 8080 8765 8099 health zombie",
        "title": "Portas OFF ou zombie",
        "body": "Porta aberta sem health = processo zombie. Reiniciar via safe_start.",
        "action": "safe_start_bridge/engine/voice",
    },
    {
        "id": "venv_deps",
        "tags": "venv missing deps fastapi uvicorn httpx pydantic psutil",
        "title": "Venv ou deps em falta",
        "body": "Criar engine/venv e pip install deps críticas.",
        "action": "pip install deps críticas",
    },
    {
        "id": "safety",
        "tags": "paper_trade execution_allowed safety invariant live",
        "title": "Violação de safety",
        "body": "PAPER_TRADE=true EXECUTION_ALLOWED=false. Nunca live.",
        "action": "Forçar env paper only",
    },
    {
        "id": "gpu_intel",
        "tags": "gpu intel rtx canvas tela branca node 3000",
        "title": "GPU Intel / tela branca",
        "body": "Chrome economia, python/ollama high. Dashboard COMPACTO.",
        "action": "aura_set_hybrid_gpu.ps1 + COMPACTO",
    },
    {
        "id": "blocked_by_data",
        "tags": "blocked_by_data paper trade fail closed odds corners",
        "title": "BLOCKED_BY_DATA",
        "body": "Fail-closed paper-trade. Não é crash. odds.corners=[] = sem mercado de canto.",
        "action": "Não tratar como crash",
    },
    {
        "id": "ids_alias",
        "tags": "fixtureid cache view alias times minuto",
        "title": "Dois fixtureIds",
        "body": "Cache vs view. Canónico = times + minuto do view.",
        "action": "remember canónico por times+minuto",
    },
    {
        "id": "grounding_snap_view",
        "tags": "grounding missing corner_events snap view analysis client chat nd",
        "title": "Grounding não lê view",
        "body": "grounding.py deve ler snapshot.view e corner_events.",
        "action": "Rever engine/grounding.py",
    },
    {
        "id": "server_lift_view",
        "tags": "server fixture_context chat sem dados view payload lift ui_state",
        "title": "server _fixture_context sem view",
        "body": "server.py deve lift de view/payload para o chat.",
        "action": "Rever engine/server.py _fixture_context",
    },
    {
        "id": "extension_chrome",
        "tags": "extensao chrome sokkerpro captura mv3 live manifest",
        "title": "Extensão Chrome inativa",
        "body": "Load unpacked pasta extensao. Domínio sokkerpro.com.",
        "action": "chrome://extensions → Load unpacked → extensao",
    },
    {
        "id": "hybrid_gpu",
        "tags": "gpu intel rtx hybrid directx ollama chrome",
        "title": "GPU híbrida",
        "body": "Chrome/Edge Intel; python.exe e ollama.exe RTX.",
        "action": "Correr aura_set_hybrid_gpu.ps1",
    },
    {
        "id": "circuit_breaker",
        "tags": "circuit breaker critical loop restart bat",
        "title": "Circuit breaker",
        "body": "5 CRITICAL seguidos: parar loop e pedir AURA_TUDO_HERMES_AUTONOMO.bat",
        "action": "Parar Hermes e relançar BAT mestre",
    },
]


@dataclass
class Hit:
    id: str
    title: str
    score: float
    action: str
    body: str


class KnowledgeIndex:
    def __init__(self, root: Path | None = None):
        self.docs = list(AURA_KB)
        if root:
            self._ingest_files(root)
            self._ingest_runbooks(root)

    def _ingest_files(self, root: Path) -> None:
        for rel in ("engine/server.py", "engine/grounding.py", "engine/features.py", "bridge/server.py"):
            p = root / rel
            if not p.exists():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")[:4000]
            except Exception:
                continue
            defs = re.findall(r"^(?:def|class|async def)\s+(\w+)", text, re.M)[:20]
            self.docs.append({
                "id": f"file_{rel.replace('/', '_')}",
                "tags": f"{rel} {' '.join(defs)}".lower(),
                "title": f"Fonte {rel}",
                "body": text[:500],
                "action": f"Rever {rel}",
            })

    def _ingest_runbooks(self, root: Path) -> None:
        latest = root / "logs_supervisor" / "runbooks" / "RUNBOOK_LATEST.md"
        if not latest.exists():
            return
        try:
            text = latest.read_text(encoding="utf-8", errors="replace")[:2500]
        except Exception:
            return
        self.docs.append({
            "id": "runbook_latest",
            "tags": "runbook ciclo findings acoes tools " + text[:400].lower(),
            "title": "Último runbook Hermes",
            "body": text[:400],
            "action": "Reusar acções do runbook anterior se o padrão repetir",
        })

    def query(self, text: str, top_k: int = 4) -> List[Hit]:
        tokens = set(re.findall(r"[a-z0-9_]{3,}", text.lower()))
        if not tokens:
            return []
        scored: List[Tuple[float, Dict]] = []
        for doc in self.docs:
            bag = set(re.findall(r"[a-z0-9_]{3,}", (doc["tags"] + " " + doc["title"]).lower()))
            inter = tokens & bag
            if not inter:
                continue
            score = len(inter) / max(1, len(tokens)) + 0.12 * len(inter)
            scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        hits = []
        for score, doc in scored[:top_k]:
            hits.append(Hit(
                id=doc["id"],
                title=doc["title"],
                score=round(score, 3),
                action=doc.get("action", ""),
                body=doc.get("body", "")[:200],
            ))
        return hits
