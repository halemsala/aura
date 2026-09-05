#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Postmortem V9 — plano P1–P4 + anomalias de score."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def find_root(explicit: str | None = None) -> Path:
    cands = []
    if explicit:
        cands.append(Path(explicit))
    cands += [Path(r"C:\aura"), Path.cwd(), Path(__file__).resolve().parents[1]]
    for c in cands:
        if (c / "engine" / "server.py").exists() or (c / "logs_supervisor").exists():
            return c.resolve()
    return Path.cwd().resolve()


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def parse_latest_txt(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"status": "UNKNOWN", "actions": [], "recs": [], "findings": []}
    if not path.exists():
        return info
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Status:\s*(\w+)", text)
    if m:
        info["status"] = m.group(1)
    m = re.search(r"score=(\d+)", text)
    if m:
        info["score"] = int(m.group(1))
    m = re.search(r"HEALTH_SCORE=(\d+)", text)
    if m:
        info["score"] = int(m.group(1))
    for line in text.splitlines():
        if re.match(r"\s*\[(FIXED|CRITICAL|HIGH|MEDIUM|LOW|INFO|OK)", line):
            info["findings"].append(line.strip())
    return info


def rank_actions(status: str, findings: List[str], history: List[Dict], score: int | None) -> List[Tuple[int, str]]:
    plans: List[Tuple[int, str]] = []
    blob = " ".join(findings).upper()

    if "VENV_MISSING" in blob or "DEPS_MISSING" in blob:
        plans.append((1, "Reparar venv: engine\\venv + pip install fastapi uvicorn httpx requests pydantic psutil"))
    if "PORT_8080_OFF" in blob or "BRIDGE_DOWN" in blob or "BRIDGE_ZOMBIE" in blob:
        plans.append((1, "Subir/reiniciar Bridge :8080 (safe_start_bridge)"))
    if "PORT_8765_OFF" in blob or "ENGINE_DOWN" in blob or "ENGINE_ZOMBIE" in blob:
        plans.append((1, "Subir/reiniciar Engine :8765 com PAPER_TRADE=true EXECUTION_ALLOWED=false"))
    if "SYNTAX_" in blob or "TRY_NEST" in blob:
        plans.append((1, "Painel → CORRIGIR ATÉ FUNCIONAR (syntax allowlisted + rollback)"))
    if "LIVE_STALE" in blob:
        plans.append((2, "Captura stale >45s — aba SokkerPRO activa + F5. NÃO reinstalar."))
    if "LIVE_LATEST_EMPTY" in blob:
        plans.append((2, "SokkerPRO live + extensão Chrome unpacked (pasta extensao)"))
    if "UI_STATE_NO_VIEW" in blob:
        plans.append((2, "Engine up sem view.home — grounding/server lift view"))
    if "GROUNDING_MISSING" in blob:
        plans.append((2, "grounding.missing preenchido — rever engine/grounding.py snap/view"))
    if "EXTENSION_MISSING" in blob:
        plans.append((2, "Carregar pasta extensao no Chrome (Load unpacked)"))
    if "OLLAMA_OFF" in blob:
        plans.append((3, "Ollama opcional — sistema corre sem LLM"))
    if "PAPER_TRADE_VIOLATION" in blob or "EXECUTION_ALLOWED_VIOLATION" in blob:
        plans.append((1, "CRÍTICO: forçar PAPER_TRADE=true EXECUTION_ALLOWED=false"))
    if "BLOCKED_BY_DATA" in blob:
        plans.append((3, "BLOCKED_BY_DATA é fail-closed paper-trade, não crash"))
    if "LIVE_STALE" in blob or "UI_STATE_NO_VIEW" in blob:
        plans.append((2, "Incidente CAPTURE_ONLY — não restart Engine; SokkerPRO + extensão + F5"))
    if "CODE_DRIFT" in blob:
        plans.append((2, "Deriva CLEAN — comparar grounding/features/server com baseline 12.7; não reinstalar"))
    if "FIXTURE_ALIAS" in blob:
        plans.append((3, "Dois fixtureIds — usar times + minuto do view"))

    if score is not None and score < 50:
        plans.append((1, f"Health score baixo ({score}/100) — Bridge+Engine antes de captura"))
    elif score is not None and score < 70:
        plans.append((2, f"Health score moderado ({score}/100) — ui/state e live_latest"))

    if history:
        statuses = [h.get("status") for h in history[-10:]]
        if statuses.count("CRITICAL") >= 3:
            plans.append((1, "≥3 CRITICAL/10 — limpar portas e AURA_TUDO_HERMES_AUTONOMO.bat"))
        scores = [int(h.get("score") or 0) for h in history[-6:] if h.get("score") is not None]
        if len(scores) >= 2 and scores[-1] <= scores[0] - 20:
            plans.append((1, f"Anomalia: score {scores[0]}→{scores[-1]} (−{scores[0]-scores[-1]})"))
        if statuses[-3:] == ["HEALTHY", "HEALTHY", "HEALTHY"]:
            plans.append((4, "3× HEALTHY — focar só qualidade da captura"))

    if status == "HEALTHY" and not plans:
        plans.append((4, "Sem urgência. Manter extensão + partida live."))
    if not plans:
        plans.append((2, "Sem padrão — abrir HERMES_AUTONOMOUS_LATEST.txt"))

    return sorted(set(plans), key=lambda x: x[0])


def main() -> int:
    ap = argparse.ArgumentParser(description="Hermes Postmortem V9")
    ap.add_argument("--root", type=str)
    args = ap.parse_args()
    root = find_root(args.root)
    log = root / "logs_supervisor"
    log.mkdir(parents=True, exist_ok=True)

    txt_info = parse_latest_txt(log / "HERMES_AUTONOMOUS_LATEST.txt")
    j = load_json(log / "HERMES_AUTONOMOUS_LATEST.json") or {}
    history = load_json(log / "hermes_history.json") or []
    memory = load_json(log / "hermes_memory.json") or {}

    status = j.get("status") or txt_info.get("status") or "UNKNOWN"
    score = j.get("health_score") or txt_info.get("score")
    findings = txt_info.get("findings") or []
    if j.get("findings"):
        findings = [f"[{f.get('severity')}] {f.get('code')}: {f.get('message')}" for f in j["findings"]]

    plans = rank_actions(status, findings, history if isinstance(history, list) else [], score)

    lines = [
        f"# Hermes V9 Postmortem — {datetime.now(timezone.utc).isoformat()}",
        f"Root: `{root}`",
        f"Status: **{status}**  score: **{score if score is not None else 'n/d'}**/100",
        f"Memória: {memory.get('stats', {}) if isinstance(memory, dict) else {}}",
        f"Histórico (n): {len(history) if isinstance(history, list) else 0}",
        "",
        "## Plano de ação",
    ]
    for pri, action in plans:
        tag = {1: "P1-URGENTE", 2: "P2-ALTO", 3: "P3-MÉDIO", 4: "P4-BAIXO"}.get(pri, f"P{pri}")
        lines.append(f"1. **{tag}** — {action}")
    lines += ["", "## Findings"]
    for f in findings[:30]:
        lines.append(f"- {f}")
    if isinstance(history, list) and history:
        lines += ["", "## Últimos ciclos"]
        for h in history[-10:]:
            lines.append(
                f"- cycle={h.get('cycle')} status={h.get('status')} "
                f"score={h.get('score')} Δ={h.get('delta')} "
                f"verify={h.get('verify')} canary={h.get('canary')}"
            )
    lines += [
        "",
        "## Comandos",
        "```bat",
        "cd /d C:\\aura",
        "AURA_HERMES_PAINEL.bat",
        "python scripts\\hermes_selftest.py",
        "python scripts\\hermes_postmortem.py --root C:\\aura",
        "```",
        "",
        "Invariantes: paper_trade=true · execution_allowed=false",
    ]
    out = log / "HERMES_POSTMORTEM_LATEST.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    print(f"\n[escrito] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
