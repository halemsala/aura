#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X - Diagnostico Inteligente E2E (V25T15-AI)
Nao confunde "servicos UP" com feed completo SokkerPRO / Matriz LIVE.

Uso:
  engine\\venv\\Scripts\\python.exe scripts\\AURA_DIAG_INTELIGENTE_E2E.py
  engine\\venv\\Scripts\\python.exe scripts\\AURA_DIAG_INTELIGENTE_E2E.py --deep
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import urllib.request
    import urllib.error
except ImportError:
    pass

ROOT = Path(os.environ.get("AURA_ROOT", r"C:\aura\AURA_QUANT_X_12.7.0"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]

BRIDGE = "http://127.0.0.1:8080"
ENGINE = "http://127.0.0.1:8765"
VOICE = "http://127.0.0.1:8099"
LOG_DIR = ROOT / "logs_instalacao"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_TXT = LOG_DIR / f"diag_inteligente_{STAMP}.txt"
REPORT_JSON = LOG_DIR / f"diag_inteligente_{STAMP}.json"

# Familias esperadas no feed COMPLETO (extensao + skill v3 + charts)
EXPECTED_FAMILIES = {
    "identity": ["fixture_id", "fixtureId", "home", "away", "league", "status", "minute"],
    "score": ["score", "score_home", "score_away", "goals"],
    "pressure_stats": [
        "pressure", "pressure_gauge", "attacks", "attacks_home", "attacks_away",
        "dangerous", "dangerous_home", "dangerous_away", "possession",
    ],
    "xg_shots": [
        "xg", "xg_home", "xg_away", "shotsOn", "shots_on_home", "shots_on_away",
        "shotsOff", "shots_off_home", "shots_off_away",
    ],
    "corners": ["corners", "corners_home", "corners_away", "corner_events", "timeline"],
    "discipline": ["cards", "yellow", "red", "fouls", "offsides"],
    "markets": ["odds", "cornerOdds", "line", "overOdds", "underOdds", "oddsSeries"],
    "charts": ["appm", "xg", "timeline", "oddsOscillation", "macdXg", "pbar", "h2h", "radar"],
    "h2h": ["h2h", "form", "rank", "head_to_head"],
    "decision": [
        "decision", "action", "signal", "corner_prob", "edge", "uncertainty",
        "risk", "data_integrity", "model",
    ],
    "quality": ["source", "capture_build", "quality", "skillReady", "freshness"],
}

lines: List[str] = []
result: Dict[str, Any] = {
    "timestamp": datetime.now().isoformat(),
    "root": str(ROOT),
    "scores": {},
    "problems": [],
    "actions": [],
    "param_count": 0,
    "param_keys": [],
    "families": {},
    "mode": "unknown",
}


def log(msg: str = "", level: str = "INFO") -> None:
    prefix = {
        "OK": "[OK]   ",
        "FAIL": "[FAIL] ",
        "WARN": "[WARN] ",
        "AI": "[AI]   ",
        "SEC": "",
        "INFO": "       ",
    }.get(level, "       ")
    if level == "SEC":
        line = f"\n==== {msg} ===="
    else:
        line = f"{prefix}{msg}"
    lines.append(line)
    colors = {"OK": "\033[92m", "FAIL": "\033[91m", "WARN": "\033[93m", "AI": "\033[96m", "SEC": "\033[96m"}
    end = "\033[0m"
    c = colors.get(level, "")
    try:
        print(f"{c}{line}{end}" if c else line)
    except Exception:
        print(line)


def http_json(url: str, timeout: float = 6.0) -> Tuple[Optional[Any], Optional[str]]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "AURA-Diag-AI/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw), None
    except Exception as e:
        return None, str(e)


def flatten(obj: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                flatten(v, key, out)
            else:
                out[key] = v
    elif isinstance(obj, list):
        out[f"{prefix}.__len__"] = len(obj)
        for i, v in enumerate(obj[:30]):
            if isinstance(v, (dict, list)):
                flatten(v, f"{prefix}[{i}]", out)
            else:
                out[f"{prefix}[{i}]"] = v
    else:
        if prefix:
            out[prefix] = obj
    return out


def leaf_count(flat: Dict[str, Any]) -> int:
    return sum(1 for k in flat if not k.endswith(".__len__"))


def family_coverage(flat_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    keys_l = [k.lower() for k in flat_keys]
    blob = " ".join(keys_l)
    out = {}
    for fam, tokens in EXPECTED_FAMILIES.items():
        hits = []
        for t in tokens:
            tl = t.lower()
            if any(tl in k for k in keys_l) or tl in blob:
                hits.append(t)
        pct = round(100.0 * len(hits) / max(len(tokens), 1), 1)
        out[fam] = {"hits": hits, "expected": tokens, "coverage_pct": pct, "ok": pct >= 40}
    return out


def detect_mode(latest: Any, ui: Any, skill: Any, flat: Dict[str, Any]) -> str:
    src = ""
    if isinstance(latest, dict):
        src = str(
            (latest.get("payload") or {}).get("source")
            or latest.get("source")
            or (latest.get("view") or {}).get("source")
            or ""
        )
    home = flat.get("home") or flat.get("view.home") or flat.get("fixture.home") or flat.get("match.home")
    if home and str(home).lower() == "aldosivi" and str(flat.get("fixture_id") or flat.get("fixtureId") or "") == "19764966":
        return "TEMPLATE_INJETADO"
    if "simulation" in str(ui).lower() or "simulad" in str(ui).lower():
        return "UI_SIMULADO"
    n = leaf_count(flat)
    if n < 15:
        return "FEED_POBRE_SIMULADO"
    if "aura-capture-webview2" in src and n < 40:
        return "CAPTURA_WEBVIEW_PARCIAL"
    if skill and isinstance(skill, dict) and skill.get("schema") in ("cornerai-skill-v3", "cornerai-skill-manual-2"):
        return "SKILL_FEED_COMPLETO"
    if "aura-capture-webview2" in src:
        return "CAPTURA_WEBVIEW_LIVE"
    if n >= 40:
        return "FEED_RICO_SEM_SOURCE"
    return "DESCONHECIDO_OU_VAZIO"


def ai_heuristic_report(mode: str, families: Dict, param_count: int, flat: Dict) -> str:
    """Analise heuristica local (sem API externa). Usa regras + cobertura."""
    notes = []
    notes.append(f"Modo detectado: {mode}")
    notes.append(f"Parametros folha no payload: {param_count}")
    weak = [k for k, v in families.items() if not v["ok"]]
    strong = [k for k, v in families.items() if v["ok"]]
    notes.append(f"Familias OK ({len(strong)}): {', '.join(strong) or '-'}")
    notes.append(f"Familias fracas ({len(weak)}): {', '.join(weak) or '-'}")

    if mode in ("TEMPLATE_INJETADO", "FEED_POBRE_SIMULADO", "UI_SIMULADO"):
        notes.append(
            "CONCLUSAO: Matriz em modo simulado/pobre. "
            "A UI do Operator OS usa snapshots de demo quando nao ha skill feed autorizado "
            "nem charts unificados (appm/xg/h2h/radar)."
        )
        notes.append(
            "CAUSA RAIZ PROVAVEL: o Desktop WebView so envia cornerai-analyst-1 raso; "
            "a extensao Chrome envia cornerai-skill-v3 + charts-unified (~80-120 campos)."
        )
        notes.append(
            "ACAO: (1) Instalar extensao da pasta extensao/ no Chrome OU "
            "(2) expandir captura WebView para skill-v3; "
            "(3) confirmar GET skill_feed_latest e charts no Bridge."
        )
    elif mode == "CAPTURA_WEBVIEW_PARCIAL":
        notes.append(
            "CONCLUSAO: Captura LIVE parcial. Placar/minuto/ataques podem estar certos, "
            "mas H2H, odds, radar, appm, macdXg e disciplina faltam -> Matriz parece 'simulada'."
        )
        notes.append(
            "ACAO: Ativar pipeline skill-feed da extensao (Atualizar JSON / skill v3) "
            "apontando para Bridge :8080 com token."
        )
    elif mode == "SKILL_FEED_COMPLETO":
        notes.append("CONCLUSAO: Skill feed completo presente. Se Matriz ainda mostra simulado, falha e no adapter UI/proxy.")
    else:
        notes.append("CONCLUSAO: Estado intermediario — ver familias fracas e actions.")

    # Sanidade placar vs minuto
    minute = flat.get("minute") or flat.get("fixture.minute") or flat.get("view.minute") or flat.get("match.minute")
    sh = flat.get("score_home") or flat.get("fixture.score.home") or flat.get("view.score.home")
    if minute is not None:
        try:
            m = int(minute)
            if m <= 5 and sh is not None and int(sh) >= 3:
                notes.append(
                    f"ALERTA SANIDADE: minuto={m} com score_home={sh} — placar pode estar lido de outro bloco "
                    f"(ex.: ranking/H2H) e nao do jogo ao vivo. Regex de placar ambigua."
                )
        except Exception:
            pass

    return "\n".join(notes)


def try_engine_analysis(fixture_id: str) -> Optional[Dict]:
    if not fixture_id:
        return None
    data, err = http_json(f"{ENGINE}/api/analysis/{fixture_id}")
    if err:
        return None
    return data if isinstance(data, dict) else None


def try_voice_ai(summary: str) -> Optional[str]:
    """Tenta Voice/GLM local se disponivel (GPU opcional no servidor de voz)."""
    payload = json.dumps({
        "message": (
            "Analise este diagnostico AURA em portugues objetivo: "
            "diga se esta em modo simulado, o que falta para feed completo SokkerPRO "
            "e 3 acoes prioritarias.\n\n" + summary[:3500]
        ),
        "fixtureId": "",
    }).encode("utf-8")
    for url in (
        f"{VOICE}/api/voice/chat",
        f"{ENGINE}/api/glm_chat",
        f"{ENGINE}/api/trader/chat",
    ):
        try:
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
                reply = data.get("reply") or data.get("message") or data.get("text") or raw
                if isinstance(reply, str) and len(reply) > 20:
                    return reply[:2000]
        except Exception:
            continue
    return None


def load_file_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true", help="Chama analysis + tenta IA local (Voice/GLM)")
    args = ap.parse_args()

    log("AURA QUANT-X - DIAGNOSTICO INTELIGENTE E2E", "SEC")
    log(f"{datetime.now().isoformat()}  ROOT={ROOT}")
    log("Objetivo: medir parametros reais vs familias SokkerPRO/skill/charts; detectar modo simulado.")

    # 1 services
    log("1. SERVICOS", "SEC")
    for name, url in (("Bridge", f"{BRIDGE}/health"), ("Engine", f"{ENGINE}/api/health"), ("Voice", f"{VOICE}/api/voice/health")):
        data, err = http_json(url)
        if err:
            log(f"{name} OFF: {err}", "FAIL")
            result["problems"].append(f"{name} offline")
        else:
            log(f"{name} UP", "OK")

    # 2 load feeds
    log("2. FEEDS", "SEC")
    latest_api, err_l = http_json(f"{BRIDGE}/api/cornerai/latest")
    skill_api, err_s = http_json(f"{BRIDGE}/api/cornerai/skill-feed")
    ui, err_u = http_json(f"{ENGINE}/api/ui/state")
    latest_file = load_file_json(ROOT / "bridge" / "live_latest.json")
    skill_file = load_file_json(ROOT / "bridge" / "skill_feed_latest.json")

    if latest_api:
        log("Bridge /api/cornerai/latest OK", "OK")
    else:
        log(f"Bridge /latest: {err_l}", "WARN")
    if skill_api:
        log("Bridge /api/cornerai/skill-feed OK", "OK")
    elif skill_file:
        log("skill_feed_latest.json em disco (API falhou ou 404)", "WARN")
    else:
        log("skill-feed AUSENTE — extensao nao publicou skill v3", "FAIL")
        result["problems"].append("skill_feed ausente")
        result["actions"].append("Instalar extensao extensao/ e clicar Atualizar JSON / skill no SokkerPRO")

    if ui:
        log(f"Engine ui/state ok={ui.get('ok')} fixtureId={ui.get('fixtureId')} home={ui.get('home')} minute={ui.get('minute')}", "OK" if ui.get("home") else "WARN")
    else:
        log(f"ui/state: {err_u}", "FAIL")

    # merge docs for flatten
    docs = []
    for d in (latest_api, latest_file, skill_api, skill_file, ui):
        if isinstance(d, dict):
            docs.append(d)
    merged: Dict[str, Any] = {}
    for d in docs:
        merged = {**merged, **d}  # shallow; flatten each

    flat_all: Dict[str, Any] = {}
    for i, d in enumerate(docs):
        flatten(d, f"doc{i}", flat_all)

    # preferred latest body
    body = latest_api or latest_file or {}
    if isinstance(body, dict) and "latest" in body and isinstance(body["latest"], dict):
        body = body["latest"]
    flat_latest = flatten(body)
    param_count = leaf_count(flat_latest)
    # also count skill if present
    skill_body = skill_api or skill_file
    if isinstance(skill_body, dict):
        flat_skill = flatten(skill_body)
        param_count_skill = leaf_count(flat_skill)
    else:
        flat_skill = {}
        param_count_skill = 0

    total_params = leaf_count(flat_all)
    result["param_count"] = total_params
    result["param_count_latest"] = param_count
    result["param_count_skill"] = param_count_skill
    result["param_keys"] = sorted(flat_all.keys())[:200]

    log("3. CONTAGEM DE PARAMETROS", "SEC")
    log(f"Parametros em /latest (folha): {param_count}", "OK" if param_count >= 20 else "FAIL")
    log(f"Parametros em skill_feed (folha): {param_count_skill}", "OK" if param_count_skill >= 40 else "WARN")
    log(f"Parametros combinados (latest+skill+ui): {total_params}", "INFO")
    log("Referencia: feed completo extensao+charts tipicamente 80-150 folhas por jogo.", "INFO")

    families = family_coverage(list(flat_all.keys()))
    result["families"] = {k: {"coverage_pct": v["coverage_pct"], "hits": v["hits"], "ok": v["ok"]} for k, v in families.items()}

    log("4. COBERTURA POR FAMILIA (SokkerPRO / skill / Matriz)", "SEC")
    for fam, info in families.items():
        lvl = "OK" if info["ok"] else "FAIL"
        log(f"{fam}: {info['coverage_pct']}% hits={info['hits']}", lvl)
        if not info["ok"]:
            result["problems"].append(f"familia fraca: {fam}")

    mode = detect_mode(body, ui, skill_body, {**flat_latest, **flat_skill})
    result["mode"] = mode
    log("5. MODO DETECTADO", "SEC")
    log(f"{mode}", "FAIL" if "SIMUL" in mode or "POBRE" in mode or "TEMPLATE" in mode else "OK")

    # charts check
    log("6. CHARTS UNIFICADOS", "SEC")
    charts = None
    if isinstance(ui, dict):
        charts = ui.get("charts") if isinstance(ui.get("charts"), dict) else None
        snap = ui.get("snapshot") if isinstance(ui.get("snapshot"), dict) else {}
        if not charts and isinstance(snap.get("charts"), dict):
            charts = snap["charts"]
    chart_names = ["appm", "xg", "timeline", "oddsOscillation", "macdXg", "pbar", "h2h", "radar"]
    if not charts:
        log("charts ausentes no ui/state — Matriz nao desenha graficos reais", "FAIL")
        result["problems"].append("charts ausentes")
        result["actions"].append("Extensao charts-unified deve publicar via CHARTS_UNIFIED / skill")
    else:
        for cn in chart_names:
            if cn in charts:
                log(f"chart.{cn} presente", "OK")
            else:
                log(f"chart.{cn} ausente", "WARN")

    # analysis
    fid = None
    if isinstance(ui, dict):
        fid = ui.get("fixtureId")
    if not fid:
        fid = flat_latest.get("fixture_id") or flat_latest.get("fixture.id") or flat_latest.get("meta.fixtureId")

    analysis = None
    if args.deep and fid:
        log("7. ANALYSIS ENGINE", "SEC")
        analysis = try_engine_analysis(str(fid))
        if analysis:
            log(f"analysis/{fid} OK keys={list(analysis.keys())[:12]}", "OK")
            result["analysis_keys"] = list(analysis.keys())[:40]
        else:
            log("analysis indisponivel", "WARN")

    log("8. ANALISE HEURISTICA (local)", "SEC")
    summary = ai_heuristic_report(mode, families, total_params, {**flat_latest, **flat_skill})
    for ln in summary.split("\n"):
        log(ln, "AI")
    result["ai_heuristic"] = summary

    if args.deep:
        log("9. IA LOCAL (Voice/GLM se disponivel)", "SEC")
        reply = try_voice_ai(summary + "\nProblems: " + "; ".join(result["problems"][:12]))
        if reply:
            log("Resposta IA local:", "AI")
            for ln in reply.split("\n")[:30]:
                log(ln, "AI")
            result["ai_local"] = reply
        else:
            log("IA local indisponivel (Voice/GLM offline ou sem rota chat)", "WARN")
            result["actions"].append("Subir Voice com modelo GLM; ou usar so heuristica")

    # GPU probe
    log("10. GPU / RUNTIME", "SEC")
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            log(f"GPU: {r.stdout.strip().splitlines()[0]}", "OK")
            result["gpu"] = r.stdout.strip().splitlines()[0]
        else:
            log("nvidia-smi sem GPU listada", "WARN")
    except Exception:
        log("nvidia-smi nao disponivel neste processo", "WARN")

    # final score
    fam_ok = sum(1 for v in families.values() if v["ok"])
    fam_tot = len(families)
    score = round(100.0 * fam_ok / fam_tot, 1)
    result["scores"] = {
        "family_coverage": score,
        "param_latest": param_count,
        "param_skill": param_count_skill,
        "param_total": total_params,
        "mode": mode,
    }

    log("RESUMO FINAL", "SEC")
    log(f"Score familias: {score}% ({fam_ok}/{fam_tot})", "OK" if score >= 60 else "FAIL")
    log(f"Modo: {mode}", "INFO")
    if result["problems"]:
        log("PROBLEMAS:", "FAIL")
        for p in result["problems"]:
            log(f"- {p}", "FAIL")
    if not result["actions"]:
        if score < 60:
            result["actions"].append("Publicar skill v3 + charts pela extensao Chrome no Bridge")
            result["actions"].append("Nao depender so do aura-capture.js do WebView para Matriz completa")
    if result["actions"]:
        log("ACOES:", "WARN")
        for a in result["actions"]:
            log(f"- {a}", "WARN")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"Relatorio TXT:  {REPORT_TXT}", "INFO")
    log(f"Relatorio JSON: {REPORT_JSON}", "INFO")

    return 0 if score >= 60 and "SIMUL" not in mode and "POBRE" not in mode and "TEMPLATE" not in mode else 2


if __name__ == "__main__":
    sys.exit(main())
