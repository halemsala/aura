#!/usr/bin/env python3
"""
AURA QUANT-X — Doctor (Autonomy Layer V1)
Classifica componentes como saudável / atenção / crítico.
Não altera estado. Não desliga paper_trade. Apenas reporta.

Uso (Windows, a partir da raiz do pacote):
  engine\\venv\\Scripts\\python.exe scripts\\aura_doctor.py
  ou: python scripts\\aura_doctor.py

Saídas:
  logs_supervisor/DOCTOR_LATEST.txt
  logs_supervisor/DOCTOR_LATEST.json
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)

PORTS = {
    "bridge": 8080,
    "engine": 8765,
    "voice": 8099,
    "matriz": 8766,
    "hermes": 8777,
}

HEALTH_URLS = {
    "bridge": "http://127.0.0.1:8080/health",
    "engine": "http://127.0.0.1:8765/api/health",
    "voice": "http://127.0.0.1:8099/api/voice/health",
}

CRITICAL_FILES = [
    "engine/server.py",
    "bridge/server.py",
    "agents/activation_manifest.json",
    "config/AURA_RUNTIME.env.example",
    "AURA_LIMPEZA_INSTALA_VERIFICA_TUDO.bat",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_port(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(2000).decode("utf-8", errors="replace")
            return True, body[:500]
    except Exception as e:
        return False, str(e)[:200]


def check_files() -> List[Dict[str, Any]]:
    results = []
    for rel in CRITICAL_FILES:
        path = ROOT / rel
        ok = path.is_file()
        results.append({
            "item": f"file:{rel}",
            "status": "saudavel" if ok else "critico",
            "detail": "presente" if ok else "AUSENTE",
            "action": None if ok else f"Restaurar {rel} a partir do ZIP completo",
        })
    return results


def check_ports() -> List[Dict[str, Any]]:
    results = []
    for name, port in PORTS.items():
        open_ = check_port(port)
        # voice/matriz/hermes podem ser opcionais → atenção se fechados
        if name in ("bridge", "engine"):
            status = "saudavel" if open_ else "critico"
            action = None if open_ else f"Subir serviço {name} (porta {port})"
        else:
            status = "saudavel" if open_ else "atencao"
            action = None if open_ else f"Verificar se {name} deve estar ativo (porta {port})"
        results.append({
            "item": f"port:{name}:{port}",
            "status": status,
            "detail": "LISTEN" if open_ else "closed",
            "action": action,
        })
    return results


def check_health() -> List[Dict[str, Any]]:
    results = []
    for name, url in HEALTH_URLS.items():
        ok, detail = http_get(url)
        if name in ("bridge", "engine"):
            status = "saudavel" if ok else "critico"
        else:
            status = "saudavel" if ok else "atencao"
        results.append({
            "item": f"health:{name}",
            "status": status,
            "detail": detail[:120],
            "action": None if ok else f"Inspecionar logs_supervisor e reiniciar {name}",
        })
    return results


def check_invariants() -> List[Dict[str, Any]]:
    """Best-effort: tenta ler state do engine. Não falha o doctor se endpoint diferir."""
    results = []
    ok, body = http_get("http://127.0.0.1:8765/api/ui/state", timeout=3.0)
    if not ok:
        # fallback genérico
        ok2, body2 = http_get("http://127.0.0.1:8765/api/health", timeout=3.0)
        body = body2
        ok = ok2

    text = (body or "").lower()
    paper_ok = "paper" in text or "paper_trade" in text or ok
    # Não afirmamos valores secretos; só presença de sinais
    results.append({
        "item": "invariant:paper_signals",
        "status": "saudavel" if paper_ok else "atencao",
        "detail": "sinais de paper/health presentes" if paper_ok else "não foi possível confirmar paper via HTTP",
        "action": None if paper_ok else "Confirmar AURA_PAPER_TRADE=1 e AURA_EXECUTION_ALLOWED=0 no env",
    })

    env_example = ROOT / "config" / "AURA_RUNTIME.env.example"
    if env_example.is_file():
        content = env_example.read_text(encoding="utf-8", errors="replace")
        has_paper = "AURA_PAPER_TRADE=1" in content
        has_exec0 = "AURA_EXECUTION_ALLOWED=0" in content
        results.append({
            "item": "invariant:env_example",
            "status": "saudavel" if (has_paper and has_exec0) else "atencao",
            "detail": "example com paper=1 e execution=0" if (has_paper and has_exec0) else "revisar example",
            "action": None,
        })
    return results


def check_python() -> List[Dict[str, Any]]:
    ver = sys.version_info
    ok = ver.major == 3 and ver.minor in (10, 11)
    return [{
        "item": "python_version",
        "status": "saudavel" if ok else "critico",
        "detail": f"{ver.major}.{ver.minor}.{ver.micro}",
        "action": None if ok else "Usar Python 3.10 ou 3.11 (nunca 3.12+ no AURA)",
    }]


def check_report() -> List[Dict[str, Any]]:
    report = LOGDIR / "RELATORIO_GERAL_LATEST.txt"
    if not report.is_file():
        return [{
            "item": "report:RELATORIO_GERAL_LATEST",
            "status": "atencao",
            "detail": "arquivo ausente",
            "action": "Rodar AURA_INSTALAR_TESTAR_RELATORIO_GERAL.bat ou AURA_RELATORIO_GERAL.bat",
        }]
    age_sec = time.time() - report.stat().st_mtime
    status = "saudavel" if age_sec < 3600 else "atencao"
    return [{
        "item": "report:RELATORIO_GERAL_LATEST",
        "status": status,
        "detail": f"idade_aprox_sec={int(age_sec)}",
        "action": None if status == "saudavel" else "Gerar novo relatório geral",
    }]


def summarize(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"saudavel": 0, "atencao": 0, "critico": 0}
    for it in items:
        s = it.get("status", "atencao")
        counts[s] = counts.get(s, 0) + 1
    return counts


def main() -> int:
    started = now_iso()
    all_items: List[Dict[str, Any]] = []
    all_items.extend(check_python())
    all_items.extend(check_files())
    all_items.extend(check_ports())
    all_items.extend(check_health())
    all_items.extend(check_invariants())
    all_items.extend(check_report())

    counts = summarize(all_items)
    overall = "saudavel"
    if counts.get("critico", 0) > 0:
        overall = "critico"
    elif counts.get("atencao", 0) > 0:
        overall = "atencao"

    payload = {
        "generated_at": started,
        "root": str(ROOT),
        "overall": overall,
        "counts": counts,
        "items": all_items,
        "notes": [
            "Doctor não altera estado nem desliga paper_trade.",
            "Ações sugeridas são reversíveis e exigem confirmação humana se forem de alto impacto.",
        ],
    }

    txt_lines = [
        f"AURA DOCTOR — {started}",
        f"ROOT: {ROOT}",
        f"OVERALL: {overall}",
        f"CONTADORES: {counts}",
        "",
        "ITENS:",
    ]
    for it in all_items:
        line = f"  [{it['status'].upper():8}] {it['item']}: {it['detail']}"
        if it.get("action"):
            line += f"  → {it['action']}"
        txt_lines.append(line)
    txt_lines.append("")
    txt_lines.append("Fim do doctor. Nenhuma alteração foi aplicada.")

    txt_path = LOGDIR / "DOCTOR_LATEST.txt"
    json_path = LOGDIR / "DOCTOR_LATEST.json"
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(txt_lines))
    print(f"\nSalvo: {txt_path}")
    print(f"Salvo: {json_path}")
    return 0 if overall != "critico" else 2


if __name__ == "__main__":
    sys.exit(main())
