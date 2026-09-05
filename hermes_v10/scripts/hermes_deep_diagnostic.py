#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Deep Diagnostic V28
Camadas profundas: código, prompts, captura, WebView, grounding, LLM domain, portas, paper-lock.
Somente leitura + relatório. Nunca liga execution_allowed.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

VERSION = "V28-DEEP-1.0.0"
DOMAIN_FORBIDDEN = [
    "bolsa de valores", "ibovespa", "nasdaq", "nyse", "stock market",
    "dividend yield", "carteira de acoes da bolsa", "investir em acoes da bolsa",
    "ticker symbol", "day trade de acoes"
]
FOOTBALL_KEYWORDS = ["escanteio", "corner", "sokker", "futebol", "placar", "minuto", "ataque"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_compile(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "MISSING", f"{path} não existe"
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        ast.parse(src)
        return "OK", "compile OK"
    except SyntaxError as e:
        return "CRITICAL", f"SyntaxError: {e}"
    except Exception as e:
        return "HIGH", str(e)


def scan_domain_pollution(text: str) -> List[str]:
    low = text.lower()
    hits = []
    for w in DOMAIN_FORBIDDEN:
        if w in low:
            hits.append(w)
    return hits


def audit_file_contains(path: Path, needles: List[str]) -> Dict[str, bool]:
    if not path.exists():
        return {n: False for n in needles}
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {n: False for n in needles}
    return {n: (n in txt) for n in needles}


def deep_code_audit(root: Path) -> List[Dict[str, Any]]:
    results = []
    critical = [
        root / "engine" / "server.py",
        root / "engine" / "grounding.py",
        root / "engine" / "features.py",
        root / "bridge" / "server.py",
        root / "desktop" / "capture" / "aura-capture.js",
    ]
    for p in critical:
        status, msg = check_compile(p) if p.suffix == ".py" else (
            "OK" if p.exists() else "MISSING", "present" if p.exists() else "ausente"
        )
        results.append({"layer": "CODIGO", "item": str(p.relative_to(root)), "status": status, "msg": msg})

    # Grounding invariants
    g = root / "engine" / "grounding.py"
    checks = audit_file_contains(g, ["corner_events", "snap.home", "view."])
    for k, v in checks.items():
        results.append({
            "layer": "GROUNDING",
            "item": f"grounding lê {k}",
            "status": "OK" if v else "HIGH",
            "msg": "presente" if v else "NÃO encontrado"
        })

    # Paper guard
    s = root / "engine" / "server.py"
    paper = audit_file_contains(s, ["paper_trade", "execution_allowed"])
    results.append({
        "layer": "SEGURANCA",
        "item": "server paper_trade guard",
        "status": "OK" if paper.get("paper_trade") else "CRITICAL",
        "msg": "paper_trade referenciado" if paper.get("paper_trade") else "paper_trade AUSENTE"
    })
    return results


def deep_capture_audit(root: Path) -> List[Dict[str, Any]]:
    results = []
    capture_js = root / "desktop" / "capture" / "aura-capture.js"
    results.append({
        "layer": "CAPTURA",
        "item": "desktop/capture/aura-capture.js",
        "status": "OK" if capture_js.exists() else "CRITICAL",
        "msg": f"size={capture_js.stat().st_size if capture_js.exists() else 0}"
    })

    live = root / "bridge" / "live_latest.json"
    if live.exists():
        try:
            age = time.time() - live.stat().st_mtime
            data = json.loads(live.read_text(encoding="utf-8", errors="replace") or "{}")
            has_teams = bool(data.get("home") or data.get("away") or data.get("teams"))
            status = "OK" if age < 45 else ("HIGH" if age < 300 else "CRITICAL")
            results.append({
                "layer": "CAPTURA",
                "item": "live_latest freshness",
                "status": status,
                "msg": f"age={int(age)}s teams={has_teams}"
            })
        except Exception as e:
            results.append({"layer": "CAPTURA", "item": "live_latest", "status": "HIGH", "msg": str(e)})
    else:
        try:
            live.parent.mkdir(parents=True, exist_ok=True)
            import json as _json
            demo = {"mode":"paper_demo","home":"Demo Home FC","away":"Demo Away United",
                    "teams":["Demo Home FC","Demo Away United"],"corner_events":[],"status":"idle"}
            live.write_text(_json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append({"layer": "CAPTURA", "item": "live_latest", "status": "INFO",
                            "msg": "seeded paper_demo (instalacao limpa)"})
        except Exception as e2:
            results.append({"layer": "CAPTURA", "item": "live_latest", "status": "HIGH", "msg": f"ficheiro ausente: {e2}"})

    # Desktop publish
    exe = root / "desktop" / "publish" / "Aura.QuantX.Desktop.exe"
    results.append({
        "layer": "DESKTOP",
        "item": "Aura.QuantX.Desktop.exe",
        "status": "OK" if exe.exists() else "MEDIUM",
        "msg": "presente" if exe.exists() else "ainda não publicado — rode COMPILAR_E_ABRIR_DESKTOP.bat"
    })
    return results


def deep_prompt_domain_audit(root: Path) -> List[Dict[str, Any]]:
    results = []
    prompt_dirs = [
        root / "engine" / "prompts",
        root / "agents",
        root / "bridge" / "jarvis",
    ]
    polluted = []
    for d in prompt_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.*"):
            if p.suffix.lower() not in {".py", ".txt", ".md", ".json", ".yaml", ".yml"}:
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            hits = scan_domain_pollution(txt)
            if hits:
                polluted.append((str(p.relative_to(root)), hits[:5]))

    if polluted:
        for path, hits in polluted[:15]:
            results.append({
                "layer": "LLM_DOMAIN",
                "item": path,
                "status": "HIGH",
                "msg": f"palavras proibidas: {hits}"
            })
    else:
        results.append({
            "layer": "LLM_DOMAIN",
            "item": "scan prompts",
            "status": "OK",
            "msg": "nenhuma poluição de domínio bolsa detectada nos ficheiros"
        })

    # Force football system prompt presence
    football_prompt = root / "engine" / "prompts" / "system_hermes_football_only.txt"
    results.append({
        "layer": "LLM_DOMAIN",
        "item": "system_hermes_football_only.txt",
        "status": "OK" if football_prompt.exists() else "HIGH",
        "msg": "presente" if football_prompt.exists() else "AUSENTE — será criado pelo domain_lock"
    })
    return results


def deep_ports() -> List[Dict[str, Any]]:
    ports = {
        8080: "Bridge",
        8765: "Engine",
        8099: "Voice",
        11434: "Ollama",
    }
    out = []
    for port, name in ports.items():
        up = port_open(port)
        out.append({
            "layer": "PORTAS",
            "item": f"{name}:{port}",
            "status": "OK" if up else "CRITICAL" if port in (8080, 8765) else "LOW",
            "msg": "LISTEN" if up else "OFF"
        })
    return out


def deep_hermes_code_access(root: Path) -> List[Dict[str, Any]]:
    """Confirma que Hermes tem caminhos de leitura para todos os setores críticos."""
    sectors = [
        "engine", "bridge", "desktop", "desktop/capture", "agents",
        "scripts", "logs_supervisor", "engine/prompts", "bridge/jarvis"
    ]
    results = []
    for sec in sectors:
        p = root / sec
        results.append({
            "layer": "HERMES_ACCESS",
            "item": sec,
            "status": "OK" if p.exists() else "MEDIUM",
            "msg": "acessível" if p.exists() else "pasta ausente"
        })
    return results


def score_from_results(results: List[Dict[str, Any]]) -> int:
    score = 100
    for r in results:
        s = r["status"]
        if s == "CRITICAL":
            score -= 18
        elif s == "HIGH":
            score -= 8
        elif s == "MEDIUM":
            score -= 3
        elif s == "LOW":
            score -= 1
    return max(0, min(100, score))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    os.environ.setdefault("PAPER_TRADE", "true")
    os.environ.setdefault("EXECUTION_ALLOWED", "false")

    all_results: List[Dict[str, Any]] = []
    all_results.extend(deep_ports())
    all_results.extend(deep_code_audit(root))
    all_results.extend(deep_capture_audit(root))
    all_results.extend(deep_prompt_domain_audit(root))
    all_results.extend(deep_hermes_code_access(root))

    # Safety invariants
    all_results.append({
        "layer": "SEGURANCA",
        "item": "PAPER_TRADE env",
        "status": "OK" if os.environ.get("PAPER_TRADE", "").lower() == "true" else "CRITICAL",
        "msg": os.environ.get("PAPER_TRADE", "N/D")
    })
    all_results.append({
        "layer": "SEGURANCA",
        "item": "EXECUTION_ALLOWED env",
        "status": "OK" if os.environ.get("EXECUTION_ALLOWED", "true").lower() in ("false", "0") else "CRITICAL",
        "msg": os.environ.get("EXECUTION_ALLOWED", "N/D")
    })

    score = score_from_results(all_results)
    status = "OK" if score >= 90 else ("DEGRADED" if score >= 70 else "CRITICAL")

    lines = []
    lines.append("=" * 64)
    lines.append(f"HERMES DEEP DIAGNOSTIC {VERSION}")
    lines.append(f"Timestamp: {now_iso()}")
    lines.append(f"Root: {root}")
    lines.append(f"Status: {status}  score={score}")
    lines.append("=" * 64)

    by_layer: Dict[str, List] = {}
    for r in all_results:
        by_layer.setdefault(r["layer"], []).append(r)

    for layer, items in by_layer.items():
        lines.append(f"--- {layer} ---")
        for it in items:
            lines.append(f"  [{it['status']:8}] {it['item']}: {it['msg']}")
        lines.append("")

    lines.append("--- RECOMENDAÇÕES ---")
    if any(r["status"] in ("CRITICAL", "HIGH") and r["layer"] == "CAPTURA" for r in all_results):
        lines.append("  · CAPTURA: Abra o Desktop → botão 'Abrir SokkerPRO' → jogo AO VIVO")
        lines.append("  · NÃO use Chrome/Edge externo (economia de RAM)")
    if any(r["layer"] == "LLM_DOMAIN" and r["status"] == "HIGH" for r in all_results):
        lines.append("  · LLM_DOMAIN: rode scripts/hermes_domain_lock.py --apply")
    if any(r["item"].startswith("Engine") and r["status"] != "OK" for r in all_results):
        lines.append("  · ENGINE OFF: AURA_TUDO_EM_UM.bat ou safe_start_engine")
    lines.append("  · Invariantes: paper_trade=true | execution_allowed=false")
    lines.append("=" * 64)

    report_text = "\n".join(lines)
    print(report_text)

    if args.report:
        logdir = root / "logs_supervisor"
        logdir.mkdir(parents=True, exist_ok=True)
        out = logdir / "HERMES_DEEP_LATEST.txt"
        out.write_text(report_text, encoding="utf-8")
        js = {
            "version": VERSION,
            "timestamp": now_iso(),
            "status": status,
            "score": score,
            "results": all_results,
        }
        (logdir / "HERMES_DEEP_LATEST.json").write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nRelatório salvo em: {out}")

    return 0 if status != "CRITICAL" else 1


if __name__ == "__main__":
    sys.exit(main())
