#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AURA Diagnostico Total — instalacao + runtime + comunicacao + erros exatos."""
from __future__ import annotations
import json, os, sys, socket, time, traceback
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(os.environ.get("AURA_ROOT", Path(__file__).resolve().parents[1])).resolve()
LOGDIR = ROOT / "logs_supervisor"
LOGDIR.mkdir(parents=True, exist_ok=True)
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_TXT = LOGDIR / f"DIAGNOSTICO_TOTAL_{TS}.txt"
OUT_JSON = LOGDIR / f"DIAGNOSTICO_TOTAL_{TS}.json"
OUT_LATEST_TXT = LOGDIR / "DIAGNOSTICO_TOTAL_LATEST.txt"
OUT_LATEST_JSON = LOGDIR / "DIAGNOSTICO_TOTAL_LATEST.json"

results = []

def add(layer: str, name: str, status: str, detail: str = "", fix: str = ""):
    results.append({
        "layer": layer, "name": name, "status": status,
        "detail": detail, "fix": fix, "ts": datetime.now().isoformat(timespec="seconds"),
    })

def http_json(url: str, timeout: float = 4.0, headers: dict | None = None):
    req = Request(url, headers=headers or {"User-Agent": "AURA-Diag/1.0"})
    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", errors="replace")
        code = getattr(r, "status", 200)
        try:
            return code, json.loads(body)
        except Exception:
            return code, {"raw": body[:500]}

def port_listen(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.8)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()

def main():
    print("=" * 64)
    print(" AURA DIAGNOSTICO TOTAL")
    print(f" Inicio: {datetime.now().isoformat(timespec='seconds')}")
    print(f" ROOT:   {ROOT}")
    print("=" * 64)

    # --- L0 arquivos ---
    critical = [
        "engine/server.py", "bridge/server.py", "desktop/MainForm.cs",
        "desktop/BrowserHost.cs", "desktop/ui/matriz_v22/index.html",
        "desktop/publish/Aura.QuantX.Desktop.exe",
        "desktop/capture/aura-capture.js",
        "engine/agents/hermes_supervisor_agent.py",
        "engine/venv/Scripts/python.exe",
        "desktop/config/desktop.json",
    ]
    for rel in critical:
        p = ROOT / rel
        if p.exists():
            add("L0_files", rel, "OK", f"size={p.stat().st_size}")
        else:
            add("L0_files", rel, "FAIL", "ausente",
                fix=f"Arquivo faltando: {p}. Reextraia o ZIP ou rode o instalador.")

    # --- L1 portas ---
    for name, port in [("Bridge", 8080), ("Engine", 8765), ("Voice", 8099), ("Ollama", 11434)]:
        ok = port_listen(port)
        add("L1_ports", f"{name}:{port}", "OK" if ok else "FAIL",
            "LISTEN" if ok else "CLOSED",
            fix="" if ok else f"Subir servico {name} na porta {port}.")

    # --- L2 health ---
    endpoints = [
        ("Bridge_health", "http://127.0.0.1:8080/health"),
        ("Engine_health", "http://127.0.0.1:8765/api/health"),
        ("Voice_health", "http://127.0.0.1:8099/api/voice/health"),
        ("Ollama_tags", "http://127.0.0.1:11434/api/tags"),
        ("Engine_ui_state", "http://127.0.0.1:8765/api/ui/state"),
        ("Engine_agents", "http://127.0.0.1:8765/api/agents"),
        ("Bridge_latest", "http://127.0.0.1:8080/api/cornerai/latest"),
    ]
    for name, url in endpoints:
        try:
            code, data = http_json(url)
            if name == "Bridge_latest":
                if code == 200:
                    add("L2_http", name, "OK", f"HTTP {code} feed presente")
                elif code == 404:
                    add("L2_http", name, "WARN", "HTTP 404 sem payload — sem captura SokkerPRO",
                        fix="No Desktop: botao SokkerPRO ou F2 → login → partida AO VIVO. Nao use Chrome externo.")
                elif code == 401:
                    add("L2_http", name, "FAIL", "HTTP 401 auth",
                        fix="CORNERAI_BRIDGE_REQUIRE_TOKEN=0 e limpe CORNERAI_BRIDGE_TOKEN, ou envie header X-CornerAI-Token.")
                else:
                    add("L2_http", name, "WARN", f"HTTP {code} {str(data)[:120]}")
            else:
                add("L2_http", name, "OK", f"HTTP {code} {str(data)[:100]}")
        except HTTPError as e:
            if name == "Bridge_latest" and e.code == 404:
                add("L2_http", name, "WARN", "HTTP 404 sem payload",
                    fix="Abra SokkerPRO no WebView do AURA (F2) com jogo ao vivo.")
            elif name == "Bridge_latest" and e.code == 401:
                add("L2_http", name, "FAIL", "HTTP 401",
                    fix="Token Bridge desalinhado. Header correto: X-CornerAI-Token.")
            else:
                add("L2_http", name, "FAIL", f"HTTP {e.code}",
                    fix=f"Endpoint {url} retornou {e.code}.")
        except Exception as e:
            add("L2_http", name, "FAIL", str(e)[:160],
                fix=f"Sem comunicacao com {url}. Servico parado ou firewall.")

    # --- L3 disco feed ---
    latest = ROOT / "bridge" / "live_latest.json"
    feed = ROOT / "bridge" / "live_feed.jsonl"
    if latest.exists() and latest.stat().st_size > 2:
        age = time.time() - latest.stat().st_mtime
        add("L3_disk", "live_latest.json", "OK" if age < 120 else "WARN",
            f"size={latest.stat().st_size} ageSec={age:.0f}",
            fix="" if age < 120 else "Feed antigo — reabra partida ao vivo no SokkerPRO interno.")
    else:
        add("L3_disk", "live_latest.json", "FAIL", "vazio ou ausente",
            fix="Sem captura. Desktop F2 → SokkerPRO → jogo AO VIVO.")

    if feed.exists():
        add("L3_disk", "live_feed.jsonl", "OK", f"size={feed.stat().st_size}")
    else:
        add("L3_disk", "live_feed.jsonl", "WARN", "ausente")

    # --- L4 UI assets / EXE ---
    ui = ROOT / "desktop" / "ui" / "matriz_v22" / "index.html"
    pub = ROOT / "desktop" / "publish" / "ui" / "matriz_v22" / "index.html"
    exe = ROOT / "desktop" / "publish" / "Aura.QuantX.Desktop.exe"
    for label, p in [("ui_source", ui), ("ui_publish", pub), ("desktop_exe", exe)]:
        add("L4_desktop", label, "OK" if p.exists() else "FAIL",
            str(p),
            fix="" if p.exists() else f"Falta {p}. Publique o Desktop ou copie ui para publish.")

    # --- L5 LLM / Ollama / VRAM hint ---
    try:
        code, data = http_json("http://127.0.0.1:11434/api/tags")
        models = [m.get("name") for m in (data.get("models") or [])]
        add("L5_llm", "ollama_models", "OK" if models else "WARN",
            ", ".join(models) if models else "nenhum modelo",
            fix="" if models else "Rode AURA_INSTALL_HERMES_OLLAMA.bat")
        prefer = ROOT / "engine" / "data" / "llm_preference.json"
        if prefer.exists():
            pref = json.loads(prefer.read_text(encoding="utf-8"))
            add("L5_llm", "preference", "OK", json.dumps(pref))
            if pref.get("glm_enabled"):
                add("L5_llm", "glm", "WARN", "glm_enabled=true", fix="Defina glm_enabled=false")
            else:
                add("L5_llm", "glm", "OK", "glm desligado")
        # probe generate to load VRAM
        try:
            body = json.dumps({"model": "llama3.2:3b", "prompt": "ok", "stream": False, "options": {"num_predict": 4}}).encode()
            req = Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as r:
                gen = json.loads(r.read().decode())
            add("L5_llm", "ollama_generate", "OK", f"response={str(gen.get('response',''))[:40]}")
        except Exception as e:
            add("L5_llm", "ollama_generate", "WARN", str(e)[:160],
                fix="Modelo nao gerou resposta. ollama run llama3.2:3b")
    except Exception as e:
        add("L5_llm", "ollama", "FAIL", str(e)[:160], fix="Suba Ollama (ollama serve)")

    # --- L6 paper invariants ---
    pt = os.environ.get("PAPER_TRADE", "true").lower() in ("1", "true", "yes")
    ex = os.environ.get("EXECUTION_ALLOWED", "false").lower() in ("1", "true", "yes")
    add("L6_safety", "paper_trade", "OK" if pt else "FAIL", f"PAPER_TRADE={os.environ.get('PAPER_TRADE')}")
    add("L6_safety", "execution_allowed", "OK" if not ex else "FAIL", f"EXECUTION_ALLOWED={os.environ.get('EXECUTION_ALLOWED')}",
        fix="Force EXECUTION_ALLOWED=false")

    # --- resumo ---
    counts = {"OK": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    status = "FAIL" if counts.get("FAIL") else ("DEGRADED" if counts.get("WARN") else "OK")

    lines = []
    lines.append("=" * 64)
    lines.append(" AURA DIAGNOSTICO TOTAL")
    lines.append(f" {datetime.now().isoformat(timespec='seconds')}  ROOT={ROOT}")
    lines.append(f" Status global: {status}  OK={counts.get('OK',0)} WARN={counts.get('WARN',0)} FAIL={counts.get('FAIL',0)}")
    lines.append("=" * 64)
    for r in results:
        lines.append(f"[{r['status']:4}] {r['layer']} | {r['name']}: {r['detail']}")
        if r.get("fix"):
            lines.append(f"       FIX → {r['fix']}")
    lines.append("=" * 64)
    lines.append(" MAPA DE COMUNICACAO")
    lines.append("  Desktop WebView → aura.local/index.html (Matriz)")
    lines.append("  Desktop F2/SokkerPRO → sokkerpro.com (captura JS → Bridge :8080/api/cornerai/feed)")
    lines.append("  Engine :8765 ← Bridge latest + UI state")
    lines.append("  Hermes/Chat → Ollama :11434 (llama3.2:3b)  GLM desligado")
    lines.append("  Voice :8099 opcional (faster_whisper se STT)")
    lines.append("=" * 64)
    fails = [r for r in results if r["status"] == "FAIL"]
    warns = [r for r in results if r["status"] == "WARN"]
    if fails:
        lines.append(" ERROS EXATOS (FAIL):")
        for r in fails:
            lines.append(f"  - {r['name']}: {r['detail']}")
            if r.get("fix"):
                lines.append(f"    → {r['fix']}")
    if warns:
        lines.append(" AVISOS (WARN):")
        for r in warns:
            lines.append(f"  - {r['name']}: {r['detail']}")
            if r.get("fix"):
                lines.append(f"    → {r['fix']}")
    lines.append("=" * 64)

    text = "\n".join(lines) + "\n"
    OUT_TXT.write_text(text, encoding="utf-8")
    OUT_LATEST_TXT.write_text(text, encoding="utf-8")
    payload = {"status": status, "counts": counts, "results": results, "root": str(ROOT)}
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_LATEST_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(text)
    print(f"TXT:  {OUT_TXT}")
    print(f"JSON: {OUT_JSON}")
    return 0 if status != "FAIL" else 2

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
