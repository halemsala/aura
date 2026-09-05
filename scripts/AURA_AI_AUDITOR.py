#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X - Auditor IA multi-camada (V25T15)
Camadas: L0 hardware, L1 processos, L2 ficheiros, L3 HTTP,
         L4 semantica, L5 schema, L6 logs, L7 LLM local (Ollama/GLM).
Nao mata processos. Nao recria venv.

  engine\\venv\\Scripts\\python.exe scripts\\AURA_AI_AUDITOR.py
  engine\\venv\\Scripts\\python.exe scripts\\AURA_AI_AUDITOR.py --loop 30
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

# Windows console: never crash on unicode
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(os.environ.get("AURA_ROOT", r"C:\aura\AURA_QUANT_X_12.7.0"))
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs_instalacao"
LOG_DIR.mkdir(parents=True, exist_ok=True)

BRIDGE, ENGINE, VOICE, OLLAMA = (
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8765",
    "http://127.0.0.1:8099",
    "http://127.0.0.1:11434",
)
MESA_MIN = 12000
FAMILIES = {
    "identity": ["fixture_id", "fixtureId", "home", "away", "league", "minute"],
    "score": ["score", "goals", "score_home", "score_away"],
    "pressure": ["pressure", "attacks", "dangerous", "possession"],
    "xg": ["xg", "shotsOn", "shots_on"],
    "corners": ["corners", "corner_events", "timeline"],
    "markets": ["odds", "overOdds", "line"],
    "charts": ["appm", "radar", "macdXg", "pbar", "oddsOscillation"],
    "h2h": ["h2h", "form", "rank"],
    "decision": ["decision", "signal", "edge", "risk", "corner_prob"],
}


def http_json(url: str, timeout: float = 5.0, data: Optional[bytes] = None) -> Tuple[Any, Optional[str]]:
    try:
        req = Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "AURA-AI-Auditor/1.0")
        if data:
            req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace")), None
    except Exception as e:
        return None, str(e)


def flatten(obj: Any, prefix: str = "", out: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if out is None:
        out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            flatten(v, key, out) if isinstance(v, (dict, list)) else out.__setitem__(key, v)
    elif isinstance(obj, list):
        out[f"{prefix}.__len__"] = len(obj)
        for i, v in enumerate(obj[:25]):
            flatten(v, f"{prefix}[{i}]", out) if isinstance(v, (dict, list)) else out.__setitem__(f"{prefix}[{i}]", v)
    elif prefix:
        out[prefix] = obj
    return out


def safe_print(s: str) -> None:
    try:
        print(s)
    except Exception:
        print(s.encode("ascii", "replace").decode("ascii"))


def tail_text(path: Path, n: int = 80) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def collect_snapshot() -> Dict[str, Any]:
    snap: Dict[str, Any] = {
        "ts": datetime.now().isoformat(),
        "root": str(ROOT),
        "layers": {},
        "findings": [],
    }

    # L0 hardware
    gpu = ""
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        gpu = (r.stdout or "").strip().splitlines()[0] if r.returncode == 0 else ""
    except Exception:
        gpu = ""
    py = sys.version.split()[0]
    snap["layers"]["L0_hardware"] = {"python": py, "gpu": gpu or None}

    # L1 processes / ports via HTTP as proxy + exe
    exe = ROOT / "desktop" / "bin" / "Aura.QuantX.Desktop.exe"
    snap["layers"]["L1_process"] = {
        "desktop_exe": exe.exists(),
        "desktop_exe_bytes": exe.stat().st_size if exe.exists() else 0,
        "working_memory": (ROOT / "engine" / "working_memory.py").exists(),
        "venv_python": (ROOT / "engine" / "venv" / "Scripts" / "python.exe").exists(),
    }

    # L2 files
    mesa = {}
    for rel in (
        "desktop/ui/matriz_v22/mesa-live.html",
        "desktop/bin/ui/matriz_v22/mesa-live.html",
        "desktop/publish/ui/matriz_v22/mesa-live.html",
    ):
        p = ROOT / rel.replace("/", os.sep)
        mesa[rel] = p.stat().st_size if p.exists() else 0
    cap = (ROOT / "desktop" / "capture" / "aura-capture.js").exists()
    snap["layers"]["L2_files"] = {"mesa_live_bytes": mesa, "capture_js": cap}

    # L3 HTTP
    health_b, err_b = http_json(f"{BRIDGE}/health")
    health_e, err_e = http_json(f"{ENGINE}/api/health")
    health_v, err_v = http_json(f"{VOICE}/api/voice/health")
    ui, err_u = http_json(f"{ENGINE}/api/ui/state")
    latest, err_l = http_json(f"{BRIDGE}/api/cornerai/latest")
    skill, err_s = http_json(f"{BRIDGE}/api/cornerai/skill-feed")
    ollama, err_o = http_json(f"{OLLAMA}/api/tags")
    snap["layers"]["L3_http"] = {
        "bridge": bool(health_b),
        "engine": bool(health_e),
        "voice": bool(health_v),
        "latest_ok": bool(latest),
        "skill_ok": bool(skill),
        "ollama": bool(ollama),
        "errors": {k: v for k, v in {
            "bridge": err_b, "engine": err_e, "voice": err_v,
            "ui": err_u, "latest": err_l, "skill": err_s, "ollama": err_o,
        }.items() if v},
        "bridge_health": health_b,
    }

    # L4 semantics
    latest_file = ROOT / "bridge" / "live_latest.json"
    age = None
    file_doc = None
    if latest_file.exists():
        age = round(time.time() - latest_file.stat().st_mtime, 1)
        try:
            file_doc = json.loads(latest_file.read_text(encoding="utf-8"))
        except Exception:
            try:
                file_doc = json.loads(latest_file.read_text(encoding="utf-8-sig"))
            except Exception:
                file_doc = None
    body = latest or file_doc or {}
    if isinstance(body, dict) and isinstance(body.get("latest"), dict):
        body = body["latest"]
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        payload = body.get("view") if isinstance(body, dict) else {}
    if not isinstance(payload, dict):
        payload = body if isinstance(body, dict) else {}
    src = str(payload.get("source") or body.get("source") or "")
    b_home = payload.get("home") or (payload.get("fixture") or {}).get("home")
    b_fid = str(payload.get("fixture_id") or (payload.get("fixture") or {}).get("id") or "")
    ui = ui if isinstance(ui, dict) else {}
    snap["layers"]["L4_semantics"] = {
        "ui_fixture": ui.get("fixtureId"),
        "ui_home": ui.get("home"),
        "ui_away": ui.get("away"),
        "ui_minute": ui.get("minute"),
        "jarvis": ui.get("jarvis_state"),
        "capture_stale": ui.get("capture_stale"),
        "bridge_home": b_home,
        "bridge_fid": b_fid,
        "source": src,
        "latest_age_sec": age if age is not None else (health_b or {}).get("latestAgeSec"),
        "feed_lines": (health_b or {}).get("feedLines"),
    }

    # L5 schema families
    flat = flatten({"ui": ui, "latest": body, "skill": skill or {}})
    keys = list(flat.keys())
    blob = " ".join(k.lower() for k in keys)
    fam = {}
    for name, toks in FAMILIES.items():
        hits = [t for t in toks if t.lower() in blob]
        fam[name] = {"pct": round(100 * len(hits) / max(len(toks), 1), 1), "hits": hits}
    snap["layers"]["L5_schema"] = {
        "leaf_count": sum(1 for k in keys if not k.endswith(".__len__")),
        "families": fam,
    }

    # L6 logs
    traces = []
    for rel in (
        "engine/runtime_engine.log",
        "logs_instalacao/desktop_host.log",
    ):
        p = ROOT / rel.replace("/", os.sep)
        if not p.exists() and "desktop_host" in rel:
            local = Path(os.environ.get("LOCALAPPDATA", "")) / "AURA_QUANT_X" / "logs" / "desktop_host.log"
            p = local if local.exists() else p
        t = tail_text(p, 60)
        if not t:
            continue
        for pat, label in (
            (r"ModuleNotFoundError:.*", "import_crash"),
            (r"Traceback \(most recent call last\)", "traceback"),
            (r"Address already in use|10048", "port_busy"),
            (r"401|bridge_auth_required", "auth_401"),
            (r"UnicodeEncodeError", "encoding"),
        ):
            if re.search(pat, t):
                traces.append({"file": str(p), "kind": label})
    snap["layers"]["L6_logs"] = {"signals": traces}

    snap["raw_ui"] = {k: ui.get(k) for k in ("ok", "fixtureId", "home", "away", "minute", "jarvis_state", "capture_stale", "paper_trade")}
    return snap


def expert_system(snap: Dict[str, Any]) -> List[Dict[str, str]]:
    """Regras deterministicas (sempre ligadas, mesmo sem LLM)."""
    f: List[Dict[str, str]] = []
    L1 = snap["layers"]["L1_process"]
    L2 = snap["layers"]["L2_files"]
    L3 = snap["layers"]["L3_http"]
    L4 = snap["layers"]["L4_semantics"]
    L5 = snap["layers"]["L5_schema"]
    L6 = snap["layers"]["L6_logs"]

    def add(layer: str, sev: str, title: str, action: str) -> None:
        f.append({"layer": layer, "sev": sev, "title": title, "action": action})

    if not L1["desktop_exe"]:
        add("L1", "CRIT", "Desktop EXE ausente", "Rode AURA_TUDO_EM_UM.bat so para recompilar o EXE. Nao faca taskkill a seguir.")
    if not L1["working_memory"]:
        add("L1", "CRIT", "working_memory.py ausente", "Copie engine\\working_memory.py do ZIP. Engine crasha no import.")
    if not L1["venv_python"]:
        add("L1", "HIGH", "venv python ausente", "AURA_TUDO_EM_UM.bat recria venv (demora). Evite limpar cache a meio da sessao.")

    for rel, sz in L2["mesa_live_bytes"].items():
        if sz == 0:
            add("L2", "HIGH", f"mesa-live.html em falta: {rel}", "Copie o HTML de 14582 bytes para ui, bin e publish.")
        elif sz < MESA_MIN:
            add("L2", "HIGH", f"mesa-live.html ANTIGO ({sz} bytes) em {rel}", "A compilacao .NET repor o HTML velho. Copy-Item depois do BAT.")

    if not L2["capture_js"]:
        add("L2", "HIGH", "aura-capture.js ausente", "Sem JS nao ha captura WebView2.")

    if not L3["bridge"]:
        add("L3", "CRIT", "Bridge OFF :8080", "Nao mate python. Suba de novo com AURA_TUDO_EM_UM ou o script do Bridge.")
    if not L3["engine"]:
        add("L3", "CRIT", "Engine OFF :8765", "powershell -File .\\scripts\\AURA_START_ENGINE_FORTE.ps1")
    if L3["errors"].get("latest") and "401" in str(L3["errors"].get("latest")):
        add("L3", "MED", "GET /latest 401", "Token do Bridge. Health pode estar OK; captura Desktop precisa do token em LOCALAPPDATA\\AURA_QUANT_X\\secure.")
    if not L3["voice"]:
        add("L3", "LOW", "Voice OFF", "Opcional. STT/TTS e GLM chat locais ficam limitados.")
    if not L3["ollama"]:
        add("L7", "LOW", "Ollama OFF :11434", "IA local profunda indisponivel. Heuristica continua a funcionar.")

    age = L4.get("latest_age_sec")
    try:
        age_f = float(age) if age is not None else None
    except Exception:
        age_f = None
    if not L4.get("ui_home"):
        add("L4", "HIGH", "ui/state sem home", "Abra 1 jogo AO VIVO na pane direita + Mesa live. SokkerPRO nao precisa login.")
    if L4.get("capture_stale") is True:
        add("L4", "HIGH", "capture_stale=True", "Captura parada. Mesa live + fixture vermelho na pane direita.")
    if age_f is not None and age_f > 45:
        add("L4", "HIGH", f"feed STALE age={age_f}s", "WebView nao esta a postMessage. Confirme Mesa live e JS inject.")
    uf, bf = str(L4.get("ui_fixture") or ""), str(L4.get("bridge_fid") or "")
    if uf and bf and uf not in ("None", "None") and bf and uf != bf:
        add("L4", "CRIT", f"FIXTURE DESSINC Engine={uf} vs Bridge={bf}", "A Matriz mostra o jogo do Engine (cache). Feche outros fixtures; deixe so o da pane direita.")
    src = str(L4.get("source") or "")
    if re.search(r"inject|template|manual|Aldosivi", src, re.I) or str(L4.get("ui_home") or "").lower() == "aldosivi":
        add("L4", "CRIT", "Template/inject detectado", "NAO rode AURA_INJETAR_LATEST_VALIDO. Use captura WebView real.")
    if L4.get("jarvis") == "DEGRADADO":
        add("L4", "MED", "jarvis=DEGRADADO", "Engine up mas feed pobre/stale. Corrija L4 primeiro.")

    weak = [n for n, v in L5["families"].items() if v["pct"] < 40]
    if weak:
        add("L5", "MED", "familias fracas: " + ", ".join(weak), "H2H/odds/charts exigem skill-feed da extensao Chrome, nao so aura-capture.js.")
    if L5["leaf_count"] < 20:
        add("L5", "HIGH", f"payload pobre ({L5['leaf_count']} folhas)", "Feed raso. Captura nao esta a enviar stats.")

    for sig in L6.get("signals") or []:
        if sig["kind"] == "import_crash":
            add("L6", "CRIT", "Traceback ModuleNotFoundError nos logs", "working_memory / PYTHONPATH. Use server.py com AURA_PATH_BOOTSTRAP.")
        elif sig["kind"] == "traceback":
            add("L6", "HIGH", f"Traceback em {sig['file']}", "Abra o log e procure a ultima excepcao.")
        elif sig["kind"] == "auth_401":
            add("L6", "MED", "401 nos logs", "Token Bridge.")

    return f


def llm_opinion(snap: Dict[str, Any], findings: List[Dict[str, str]]) -> Optional[str]:
    brief = {
        "L3": snap["layers"]["L3_http"],
        "L4": snap["layers"]["L4_semantics"],
        "L5": {k: v["pct"] for k, v in snap["layers"]["L5_schema"]["families"].items()},
        "findings": findings[:12],
    }
    prompt = (
        "Voce e o auditor AURA QUANT-X. Responda em portugues, curto. "
        "1) modo real vs simulado 2) top 3 causas 3) 3 acoes. "
        "Nao invente servicos down se L3 diz up. JSON de contexto:\n"
        + json.dumps(brief, ensure_ascii=False, default=str)[:3500]
    )
    payload = json.dumps({"model": "glm4:9b-chat-q4_0", "prompt": prompt, "stream": False, "message": prompt}).encode("utf-8")

    # Ollama generate
    data, err = http_json(f"{OLLAMA}/api/generate", timeout=25, data=json.dumps({
        "model": os.environ.get("CORNERAI_CHAT_MODEL", "glm4:9b-chat-q4_0"),
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8"))
    if isinstance(data, dict) and data.get("response"):
        return str(data["response"])[:1800]

    for url in (f"{ENGINE}/api/glm_chat", f"{ENGINE}/api/trader/chat", f"{VOICE}/api/voice/chat"):
        data, err = http_json(url, timeout=20, data=json.dumps({"message": prompt, "fixtureId": ""}).encode("utf-8"))
        if isinstance(data, dict):
            reply = data.get("reply") or data.get("message") or data.get("text")
            if isinstance(reply, str) and len(reply) > 20:
                return reply[:1800]
    return None


def render(snap: Dict[str, Any], findings: List[Dict[str, str]], llm: Optional[str]) -> str:
    lines: List[str] = []
    def L(s: str = "") -> None:
        lines.append(s)
        safe_print(s)

    L("=" * 62)
    L("AURA AI AUDITOR  multi-camada  " + snap["ts"])
    L("=" * 62)
    L0 = snap["layers"]["L0_hardware"]
    L(f"L0  python={L0['python']}  gpu={L0['gpu'] or 'n/d'}")
    L1 = snap["layers"]["L1_process"]
    L(f"L1  exe={L1['desktop_exe']}  wm={L1['working_memory']}  venv={L1['venv_python']}")
    L3 = snap["layers"]["L3_http"]
    L(f"L3  Bridge={L3['bridge']} Engine={L3['engine']} Voice={L3['voice']} Ollama={L3['ollama']}")
    L4 = snap["layers"]["L4_semantics"]
    L(f"L4  {L4.get('ui_home')} x {L4.get('ui_away')} min={L4.get('ui_minute')} fid={L4.get('ui_fixture')} jarvis={L4.get('jarvis')}")
    L(f"    source={L4.get('source')} age={L4.get('latest_age_sec')} stale={L4.get('capture_stale')}")
    L5 = snap["layers"]["L5_schema"]
    fams = " ".join(f"{k}:{v['pct']}%" for k, v in L5["families"].items())
    L(f"L5  folhas={L5['leaf_count']}  {fams}")
    L(f"L6  sinais_log={len(snap['layers']['L6_logs']['signals'])}")
    L("")
    if not findings:
        L("[OK] Nenhuma falha estrutural. Camadas altas OK.")
    else:
        L(f"ACHADOS ({len(findings)}):")
        for i, x in enumerate(findings, 1):
            L(f"  {i}. [{x['sev']}] {x['layer']}  {x['title']}")
            L(f"      -> {x['action']}")
    L("")
    L("L7 LLM:")
    if llm:
        for ln in llm.splitlines()[:18]:
            L("  " + ln)
    else:
        L("  (Ollama/GLM indisponivel - usou so o motor de regras)")
    L("=" * 62)
    crit = sum(1 for x in findings if x["sev"] == "CRIT")
    high = sum(1 for x in findings if x["sev"] == "HIGH")
    L(f"SCORE  CRIT={crit} HIGH={high} TOTAL={len(findings)}")
    return "\n".join(lines)


def run_once() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = collect_snapshot()
    findings = expert_system(snap)
    llm = llm_opinion(snap, findings)
    text = render(snap, findings, llm)
    out = {
        "snapshot": snap,
        "findings": findings,
        "llm": llm,
    }
    (LOG_DIR / f"ai_auditor_{stamp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (LOG_DIR / f"ai_auditor_{stamp}.txt").write_text(text, encoding="utf-8")
    safe_print(f"Relatorio: {LOG_DIR / f'ai_auditor_{stamp}.txt'}")
    if any(x["sev"] == "CRIT" for x in findings):
        return 2
    if findings:
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=0, help="Repetir a cada N segundos (0 = uma vez)")
    args = ap.parse_args()
    if args.loop <= 0:
        return run_once()
    code = 0
    while True:
        code = run_once()
        safe_print(f"(loop {args.loop}s  Ctrl+C para parar)\n")
        time.sleep(max(8, args.loop))
    return code


if __name__ == "__main__":
    sys.exit(main())
