#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA SENTINELA - envia TODO o feed + snapshot visual para a IA, sem supervisao.
Corre em loop. So imprime alerta se CRIT/HIGH. Arquiva dumps completos.

  engine\\venv\\Scripts\\python.exe scripts\\AURA_AI_SENTINEL.py
  engine\\venv\\Scripts\\python.exe scripts\\AURA_AI_SENTINEL.py --loop 20
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

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
DUMP = LOG_DIR / "sentinel_dumps"
VIS = LOG_DIR / "visual"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DUMP.mkdir(parents=True, exist_ok=True)
VIS.mkdir(parents=True, exist_ok=True)

BRIDGE, ENGINE, VOICE, OLLAMA = (
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8765",
    "http://127.0.0.1:8099",
    "http://127.0.0.1:11434",
)


def sp(s: str) -> None:
    try:
        print(s)
    except Exception:
        print(s.encode("ascii", "replace").decode("ascii"))


def http_json(url: str, timeout: float = 6.0, data: Optional[bytes] = None) -> Tuple[Any, Optional[str]]:
    try:
        req = Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "AURA-Sentinel/1.0")
        if data:
            req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace")), None
    except Exception as e:
        return None, str(e)


def load_file(p: Path) -> Any:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        try:
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"_raw": p.read_text(encoding="utf-8", errors="replace")[:8000]}


def screenshot() -> Optional[str]:
    ps1 = ROOT / "scripts" / "AURA_CAPTURE_VISUAL.ps1"
    if not ps1.exists():
        return None
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1), "-OutDir", str(VIS)],
            capture_output=True, text=True, timeout=20,
        )
        path = (r.stdout or "").strip().splitlines()
        return path[-1] if path else None
    except Exception:
        return None


def collect_all() -> Dict[str, Any]:
    pack: Dict[str, Any] = {"ts": datetime.now().isoformat(), "root": str(ROOT)}
    pack["health_bridge"], pack["err_bridge"] = http_json(f"{BRIDGE}/health")
    pack["health_engine"], pack["err_engine"] = http_json(f"{ENGINE}/api/health")
    pack["health_voice"], pack["err_voice"] = http_json(f"{VOICE}/api/voice/health")
    pack["ui"], pack["err_ui"] = http_json(f"{ENGINE}/api/ui/state")
    pack["latest_api"], pack["err_latest"] = http_json(f"{BRIDGE}/api/cornerai/latest")
    pack["skill_api"], pack["err_skill"] = http_json(f"{BRIDGE}/api/cornerai/skill-feed")
    pack["latest_file"] = load_file(ROOT / "bridge" / "live_latest.json")
    pack["skill_file"] = load_file(ROOT / "bridge" / "skill_feed_latest.json")
    fid = None
    if isinstance(pack["ui"], dict):
        fid = pack["ui"].get("fixtureId")
    pack["analysis"] = None
    if fid:
        pack["analysis"], pack["err_analysis"] = http_json(f"{ENGINE}/api/analysis/{fid}")
    else:
        pack["err_analysis"] = "no fixture"
    # visual
    shot = screenshot()
    pack["screenshot"] = shot
    pack["visual_meta"] = load_file(VIS / "latest_visual.json")
    # mesa live size (visual contract of UI)
    mesa = {}
    for rel in (
        "desktop/ui/matriz_v22/mesa-live.html",
        "desktop/bin/ui/matriz_v22/mesa-live.html",
    ):
        p = ROOT / rel.replace("/", os.sep)
        mesa[rel] = p.stat().st_size if p.exists() else 0
    pack["mesa_live_bytes"] = mesa
    pack["exe"] = (ROOT / "desktop" / "bin" / "Aura.QuantX.Desktop.exe").exists()
    return pack


def compact_for_llm(pack: Dict[str, Any]) -> Dict[str, Any]:
    """Tudo o que a IA precisa sem 2MB de JSON."""
    ui = pack.get("ui") if isinstance(pack.get("ui"), dict) else {}
    latest = pack.get("latest_api") or pack.get("latest_file") or {}
    if isinstance(latest, dict) and isinstance(latest.get("latest"), dict):
        latest = latest["latest"]
    payload = latest.get("payload") if isinstance(latest, dict) else {}
    if not isinstance(payload, dict):
        payload = latest.get("view") if isinstance(latest, dict) else {}
    if not isinstance(payload, dict):
        payload = latest if isinstance(latest, dict) else {}
    skill = pack.get("skill_api") or pack.get("skill_file") or {}
    skill_keys = list(skill.keys())[:40] if isinstance(skill, dict) else []
    hb = pack.get("health_bridge") or {}
    return {
        "ts": pack.get("ts"),
        "services": {
            "bridge": bool(pack.get("health_bridge")),
            "engine": bool(pack.get("health_engine")),
            "voice": bool(pack.get("health_voice")),
            "exe": pack.get("exe"),
        },
        "bridge_health": {"feedLines": hb.get("feedLines"), "latestAgeSec": hb.get("latestAgeSec")},
        "ui": {
            "fixtureId": ui.get("fixtureId"),
            "home": ui.get("home"),
            "away": ui.get("away"),
            "minute": ui.get("minute"),
            "jarvis": ui.get("jarvis_state"),
            "stale": ui.get("capture_stale"),
            "paper_trade": ui.get("paper_trade"),
        },
        "capture": {
            "source": payload.get("source"),
            "home": payload.get("home") or (payload.get("fixture") or {}).get("home"),
            "away": payload.get("away") or (payload.get("fixture") or {}).get("away"),
            "fid": payload.get("fixture_id") or (payload.get("fixture") or {}).get("id"),
            "minute": payload.get("minute") or (payload.get("fixture") or {}).get("minute"),
            "pressure": payload.get("pressure") or payload.get("pressure_gauge"),
            "attacks": payload.get("attacks") or {
                "home": payload.get("attacks_home"),
                "away": payload.get("attacks_away"),
            },
            "xg": {"home": payload.get("xg_home"), "away": payload.get("xg_away")},
            "corners": payload.get("corners"),
            "quality": payload.get("quality"),
        },
        "skill_keys": skill_keys,
        "analysis_ok": bool(pack.get("analysis")),
        "mesa_live_bytes": pack.get("mesa_live_bytes"),
        "screenshot": pack.get("screenshot"),
        "http_errors": {k: pack.get(k) for k in ("err_bridge", "err_engine", "err_ui", "err_latest") if pack.get(k)},
    }


def rules(c: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    def add(sev, title, action):
        out.append({"sev": sev, "title": title, "action": action})
    s = c["services"]
    if not s["bridge"]:
        add("CRIT", "Bridge down", "Nao mate python. Suba Bridge.")
    if not s["engine"]:
        add("CRIT", "Engine down", "AURA_START_ENGINE_FORTE.ps1")
    if not s["exe"]:
        add("HIGH", "Desktop EXE ausente", "AURA_TUDO_EM_UM.bat uma vez")
    ui, cap = c["ui"], c["capture"]
    if not ui.get("home"):
        add("HIGH", "Matriz sem home", "1 jogo AO VIVO na pane direita + Mesa live")
    if ui.get("stale") is True:
        add("HIGH", "capture_stale", "WebView parado")
    age = (c.get("bridge_health") or {}).get("latestAgeSec")
    try:
        if age is not None and float(age) > 45:
            add("HIGH", f"feed stale {age}s", "Mesa live + fixture vermelho")
    except Exception:
        pass
    uf, bf = str(ui.get("fixtureId") or ""), str(cap.get("fid") or "")
    if uf and bf and uf != bf and uf != "None":
        add("CRIT", f"fixture dessinc Engine={uf} Bridge={bf}", "Um so jogo na pane direita")
    if str(ui.get("home") or "").lower() == "aldosivi":
        add("CRIT", "template inject", "Nao usar AURA_INJETAR_LATEST_VALIDO")
    for rel, sz in (c.get("mesa_live_bytes") or {}).items():
        if int(sz or 0) < 12000:
            add("HIGH", f"mesa-live antigo {sz} {rel}", "Copy-Item HTML 14582 para bin")
    if not c.get("screenshot"):
        add("MED", "screenshot falhou", "PowerShell captura de ecran")
    return out


def ask_llm(c: Dict[str, Any], findings: List[Dict[str, str]], shot: Optional[str]) -> Optional[str]:
    prompt = (
        "Auditor autonomo AURA QUANT-X. Portugues curto.\n"
        "Dados REAIS do sistema (nao invente servicos down se services=true).\n"
        "1) captura real ou simulada 2) erros ocultos 3) minuto coerente com o jogo "
        "4) se a Mesa live (HTML size) e o screenshot existem 5) 3 acoes.\n"
        "CONTEXTO:\n" + json.dumps({"compact": c, "findings": findings}, ensure_ascii=False, default=str)[:4000]
    )
    # vision if llava-like model present
    tags, _ = http_json(f"{OLLAMA}/api/tags", timeout=4)
    models = []
    if isinstance(tags, dict):
        models = [str(m.get("name") or "") for m in (tags.get("models") or [])]
    vision = next((m for m in models if any(x in m.lower() for x in ("llava", "vision", "minicpm-v", "qwen2.5vl"))), None)
    chat_model = os.environ.get("CORNERAI_CHAT_MODEL") or next(
        (m for m in models if "glm" in m.lower() or "llama" in m.lower() or "qwen" in m.lower()),
        (models[0] if models else "glm4:9b-chat-q4_0"),
    )

    if vision and shot and Path(shot).exists():
        try:
            b64 = base64.b64encode(Path(shot).read_bytes()).decode("ascii")
            body = {
                "model": vision,
                "prompt": prompt + "\nAnalise tambem a imagem do ecran AURA/SokkerPRO.",
                "images": [b64],
                "stream": False,
            }
            data, _ = http_json(f"{OLLAMA}/api/generate", timeout=60, data=json.dumps(body).encode("utf-8"))
            if isinstance(data, dict) and data.get("response"):
                return str(data["response"])[:2000]
        except Exception:
            pass

    data, _ = http_json(
        f"{OLLAMA}/api/generate",
        timeout=35,
        data=json.dumps({"model": chat_model, "prompt": prompt, "stream": False}).encode("utf-8"),
    )
    if isinstance(data, dict) and data.get("response"):
        return str(data["response"])[:2000]
    for url in (f"{ENGINE}/api/glm_chat", f"{ENGINE}/api/trader/chat"):
        data, _ = http_json(url, timeout=20, data=json.dumps({"message": prompt, "fixtureId": c.get("ui", {}).get("fixtureId") or ""}).encode("utf-8"))
        if isinstance(data, dict):
            r = data.get("reply") or data.get("message")
            if isinstance(r, str) and len(r) > 20:
                return r[:2000]
    return None


def tick(quiet_ok: bool = True) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pack = collect_all()
    dump_path = DUMP / f"dump_{stamp}.json"
    # full dump (may be large)
    dump_path.write_text(json.dumps(pack, ensure_ascii=False, default=str), encoding="utf-8")
    # keep last 40 dumps
    dumps = sorted(DUMP.glob("dump_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in dumps[40:]:
        try:
            old.unlink()
        except Exception:
            pass
    c = compact_for_llm(pack)
    findings = rules(c)
    llm = ask_llm(c, findings, pack.get("screenshot"))
    report = {
        "ts": pack["ts"],
        "compact": c,
        "findings": findings,
        "llm": llm,
        "dump": str(dump_path),
        "screenshot": pack.get("screenshot"),
    }
    (LOG_DIR / "sentinel_latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    crit = [x for x in findings if x["sev"] in ("CRIT", "HIGH")]
    ui = c["ui"]
    line = (
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"{ui.get('home')} x {ui.get('away')} min={ui.get('minute')} "
        f"fid={ui.get('fixtureId')} age={c['bridge_health'].get('latestAgeSec')} "
        f"shot={'yes' if pack.get('screenshot') else 'no'} "
        f"findings={len(findings)} CRIT/HIGH={len(crit)}"
    )
    if crit or not quiet_ok:
        sp(line)
        for x in findings:
            sp(f"  [{x['sev']}] {x['title']} -> {x['action']}")
        if llm:
            sp("  [IA] " + " ".join(llm.split())[:500])
    else:
        sp(line + "  OK (silencio: sem CRIT/HIGH)")
    (LOG_DIR / "sentinel.log").open("a", encoding="utf-8").write(line + "\n")
    return 2 if any(x["sev"] == "CRIT" for x in findings) else (1 if crit else 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", type=int, default=20)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    sp("AURA SENTINELA  dump completo + screenshot + IA local")
    sp("Nao mata processos. Ctrl+C para parar.")
    sp(f"Dumps: {DUMP}")
    sp(f"Visual: {VIS}")
    if args.once:
        return tick(quiet_ok=not args.verbose)
    code = 0
    while True:
        code = tick(quiet_ok=not args.verbose)
        time.sleep(max(10, args.loop))
    return code


if __name__ == "__main__":
    sys.exit(main())
