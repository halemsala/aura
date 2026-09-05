"""CornerAI Skill Runtime 10.2.
Loads the authoritative .skill file, exposes production gates, structured chat actions,
and append-only REG/session memory required by the installed skill.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

BASE = Path(__file__).resolve().parent
SKILL_PATH = BASE / "skills" / "CornerAI_v10.2_ELITE.skill"
ARTIFACTS = BASE / "artifacts"
REG_PATH = ARTIFACTS / "CornerAI_REG_Analises_Entradas.jsonl"
REG_MD_PATH = ARTIFACTS / "CornerAI_Log_Analises_Entradas.md"
SESSION_PATH = ARTIFACTS / "SESSION-STATE.md"
RECENT_PATH = ARTIFACTS / "RECENT_CONTEXT.md"

ARTIFACTS.mkdir(parents=True, exist_ok=True)


def _read_skill() -> str:
    try:
        return SKILL_PATH.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def skill_info() -> Dict[str, Any]:
    text = _read_skill()
    head = "\n".join(text.splitlines()[:12])
    version = re.search(r'^version:\s*["\']?([^"\'\n]+)', head, re.MULTILINE)
    name = re.search(r'^name:\s*([^\n]+)', head, re.MULTILINE)
    return {
        "installed": bool(text),
        "name": (name.group(1).strip() if name else "cornerai"),
        "version": (version.group(1).strip() if version else "unknown"),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "path": str(SKILL_PATH),
        "size_bytes": len(text.encode("utf-8")),
        "authoritative": "FIM DO CORNERAI 10.0" in text or "FAIL-CLOSED DE PRODUÇÃO" in text,
    }


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _next_reg_id() -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"REG-{day}-"
    n = 0
    try:
        if REG_PATH.exists():
            for line in REG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("{"):
                    try:
                        rec = json.loads(line)
                        rid = str(rec.get("id") or "")
                        if rid.startswith(prefix):
                            n = max(n, int(rid.rsplit("-", 1)[-1]))
                    except Exception:
                        continue
    except Exception:
        pass
    return f"{prefix}{n + 1:03d}"


def append_reg(record_type: str, payload: Dict[str, Any]) -> str:
    rid = _next_reg_id()
    rec = {
        "id": rid,
        "timestamp": _iso(),
        "type": record_type,
        "skill_version": skill_info().get("version"),
        **payload,
    }
    with REG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    if not REG_MD_PATH.exists():
        REG_MD_PATH.write_text("# CornerAI Log de Análises e Entradas\n\n", encoding="utf-8")
    with REG_MD_PATH.open("a", encoding="utf-8") as f:
        f.write(f"## {rid} · {record_type}\n\n- Timestamp: {rec['timestamp']}\n- Fixture: {payload.get('fixtureId') or '-'}\n- Decisão: {payload.get('decision') or '-'}\n- Mensagem: {payload.get('message') or '-'}\n\n")
    return rid


def update_memory(fixture_id: Optional[str], note: str, analysis: Optional[Dict[str, Any]] = None) -> None:
    if not SESSION_PATH.exists():
        SESSION_PATH.write_text(
            "# SESSION-STATE\n\n## Regras instaladas\n- CornerAI Skill 10.2 ativa.\n- Execução fail-closed.\n- Não transformar `no_data` em zero.\n- DecisionGate é o único dono da decisão final.\n\n",
            encoding="utf-8",
        )
    recent = RECENT_PATH.read_text(encoding="utf-8") if RECENT_PATH.exists() else "# RECENT_CONTEXT\n\n"
    entry = f"- {_iso()} | fixture={fixture_id or '-'} | {note}\n"
    if analysis:
        entry += f"  - decisão={analysis.get('decision') or analysis.get('signal')} prob={analysis.get('corner_prob')} regime={analysis.get('regime')}\n"
    RECENT_PATH.write_text(recent + entry, encoding="utf-8")


def _data_quality(analysis: Dict[str, Any]) -> Dict[str, Any]:
    # Conservative checks aligned to the skill. Unknown values are not converted to zero.
    issues = []
    minute = analysis.get("minute")
    if minute is None:
        issues.append("clock_missing")
    stats = analysis.get("stats") or {}
    corners = stats.get("corners") or {}
    for side in ("home", "away"):
        value = corners.get(side)
        if value is not None:
            try:
                if float(value) < 0:
                    issues.append(f"corners_negative_{side}")
            except Exception:
                issues.append(f"corners_invalid_{side}")
    return {
        "status": "BLOCK" if issues else "VALID",
        "issues": issues,
        "completeness": 1.0 if not issues else 0.0,
    }


def _decision_from_analysis(a: Dict[str, Any], message: str) -> str:
    signal = str(a.get("signal") or "HOLD")
    try:
        p = float(a.get("corner_prob") or 0.0)
    except Exception:
        p = 0.0
    dq = a.get("skill_data_quality") or {}
    if dq.get("status") == "BLOCK":
        return "BLOCK"
    if signal == "BUY_CORNER":
        return "ENTRA"
    if signal in {"WATCH_CORNER", "WATCH_ATTACK", "ATTACK_IMMINENT"}:
        return "AGUARDA"
    if p < 0.28:
        return "NAO_ENTRA"
    return "AGUARDA"


_ANALYSIS_KEYWORDS = (
    "analis", "anális", "status", "decis", "entra", "aguarda", "corner", "escanteio",
    "jogo", "partida", "placar", "risco", "kelly", "odds", "edge", "pressão", "pressao",
    "regime", "gate", "reg", "dados", "mercado", "atualizar", "próx", "prox",
)

print("[skill_runtime] build CHATFIX4 carregado — filtro de intenção de análise ATIVO")


def _is_analysis_request(message: str) -> bool:
    """Só entra no fluxo de card de análise se a mensagem claramente pedir isso
    (palavra-chave do domínio, ou um dos quick_replies/actions pré-definidos).
    Sem isso, qualquer mensagem digitada (mesmo 'oi' ou 'que horas são') caía
    sempre no card fixo de decisão, porque o texto do usuário não era checado."""
    m = (message or "").strip().lower()
    if not m:
        return False
    return any(kw in m for kw in _ANALYSIS_KEYWORDS)


def build_interactive_chat(message: str, analysis: Optional[Dict[str, Any]], fixture_id: Optional[str]) -> Dict[str, Any]:
    a = dict(analysis or {})

    if not _is_analysis_request(message):
        print(f"[skill_runtime] msg='{message}' -> NÃO é análise -> resposta curta")
        # Mensagem não pede análise de jogo -> não monta o card fixo. Responde
        # curto e direto, sem inventar dados fora do que a skill sabe.
        reply = (
            "Esse chat é o painel operacional do CornerAI — foco em análise de "
            "escanteios e gestão de risco da partida. Pergunte algo como "
            "'como está o jogo', 'mostra a decisão' ou 'simula o risco' para eu "
            "puxar os dados ao vivo."
        )
        return {
            "ok": True,
            "schema": "cornerai-interactive-chat-1",
            "skill": skill_info(),
            "decision": None,
            "signal": None,
            "reply": reply,
            "analysis": a or None,
            "ui": None,
        }

    print(f"[skill_runtime] msg='{message}' -> É análise -> card")
    teams = a.get("teams") or {}
    home = teams.get("home") or a.get("home") or "?"
    away = teams.get("away") or a.get("away") or "?"
    decision = _decision_from_analysis(a, message)
    def _pct(v):
        if v is None or v == "":
            return "N/D"
        try:
            return f"{float(v):.1%}"
        except (TypeError, ValueError):
            return "N/D"
    p_txt = _pct(a.get("corner_prob"))
    gp_txt = _pct(a.get("goal_prob"))
    minute = a.get("minute")
    dq = a.get("skill_data_quality") or _data_quality(a)
    regime = a.get("skill_regime") or a.get("strategy") or "unknown"
    kills = a.get("skill_kills") or []
    kelly = float(a.get("kelly") or 0.0)
    odds = (a.get("analytics") or {}).get("odds")

    lines = [
        f"🏟️ **{home} × {away} | {minute if minute is not None else '—'}'**",
        f"🎯 **Decisão:** `{decision}`",
        f"📈 **P(corner):** {p_txt} · **P(gol):** {gp_txt}",
        f"🧠 **Regime:** `{regime}` · **Qualidade:** `{dq.get('status', 'UNKNOWN')}`",
    ]
    if odds is not None:
        lines.append(f"💰 **Odd observada:** {float(odds):.2f}")
    if kelly > 0:
        lines.append(f"🛡️ **Kelly fracionado:** {kelly:.2%}")
    if kills:
        lines.append("⛔ **Kills:** " + ", ".join(map(str, kills[:4])))
    if decision == "ENTRA":
        lines.append("✅ Gate aprovado pelo motor local.")
    elif decision == "BLOCK":
        lines.append("🛑 Gate bloqueado por qualidade/safety.")
    else:
        lines.append("⏳ Sem confirmação suficiente para entrada.")

    quick = [
        "🔄 Atualizar jogo",
        "📊 Mostrar dados completos",
        "🚩 Analisar próximos 5 min",
        "📈 Explicar pressão",
        "💰 Ver odds e edge",
        "🛡️ Simular risco",
        "🧾 Mostrar REG",
    ]
    rid = append_reg("ANALISE_LIVE" if fixture_id else "ANALISE_PRE", {
        "fixtureId": fixture_id,
        "message": message,
        "decision": decision,
        "analysis": a,
    })
    update_memory(fixture_id, f"chat: {message}", {**a, "decision": decision})

    return {
        "ok": True,
        "schema": "cornerai-interactive-chat-1",
        "skill": skill_info(),
        "decision": decision,
        "signal": a.get("signal") or "HOLD",
        "reply": "\n".join(lines),
        "analysis": a,
        "ui": {
            "ui_action": True,
            "game_id": fixture_id or a.get("fixtureId"),
            "quick_replies": quick,
            "actions": [
                {"id": "refresh", "label": "🔄 Atualizar", "command": "REFRESH_GAME"},
                {"id": "details", "label": "📊 Dados", "command": "SHOW_DATA"},
                {"id": "next5", "label": "🚩 Próx. 5m", "command": "ANALYZE_NEXT_5"},
                {"id": "pressure", "label": "📈 Pressão", "command": "EXPLAIN_PRESSURE"},
                {"id": "odds", "label": "💰 Odds/Edge", "command": "SHOW_MARKET"},
                {"id": "risk", "label": "🛡️ Risco", "command": "SIMULATE_RISK"},
                {"id": "reg", "label": "🧾 REG", "command": "SHOW_REG", "payload": {"id": rid}},
            ],
            "copy_payload": f"[CornerAI] {home} x {away} · {decision} · P(corner 5m)={p_txt}",
        },
        "reg_id": rid,
    }
