# -*- coding: utf-8 -*-
"""AURA — boot permanente da Matriz (nao simulado).
Copia UI/captura, sobe nucleo, mede ui/state, reinicia Desktop.
Nao inventa fixture. LIVE so se o Engine tiver home/away.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / "bridge" / "server.py").exists() else HERE
LOCAL = Path(os.environ.get("LOCALAPPDATA", "")) / "AURA_QUANT_X"
PORTABLE = LOCAL / "portable"
ENGINE = "http://127.0.0.1:8765"
BRIDGE = "http://127.0.0.1:8080"


def http(method, url, payload=None, headers=None, timeout=4.0):
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    data = None
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw[:300]}
            return resp.status, body, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw[:300]}
        return e.code, body, "HTTP %s" % e.code
    except Exception as e:
        return None, {}, str(e)


def find_python():
    for p in [
        ROOT / "engine" / "venv" / "Scripts" / "python.exe",
        PORTABLE / "engine" / "venv" / "Scripts" / "python.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe",
    ]:
        if p.exists():
            return p
    return None


def find_exe():
    # V25Q-ORIGINAL-UI: nunca reabrir a copia antiga em %LOCALAPPDATA%\AURA_QUANT_X\portable.
    # A copia atual (ROOT/desktop/publish) e sempre a unica fonte valida.
    for p in [
        ROOT / "desktop" / "publish" / "Aura.QuantX.Desktop.exe",
    ]:
        if p.exists():
            return p
    return None


def copy_matrix_assets():
    # V25Q-ORIGINAL-UI: nao propaga mais nada para %LOCALAPPDATA%\AURA_QUANT_X\portable
    # (essa pasta e a copia antiga que o Operator OS nao deve reabrir) e nunca mais
    # copia ou referencia mesa-live.html, que foi removido do fluxo normal.
    copied = []
    pairs = [
        (ROOT / "desktop" / "ui" / "matriz_v22" / "aura-desktop-boot.js", PORTABLE / "desktop" / "ui" / "matriz_v22" / "aura-desktop-boot.js"),
    ]
    bundle = ROOT / "desktop" / "ui" / "matriz_v22" / "assets" / "index-aCoLBegj.js"
    if bundle.exists():
        pairs.append((bundle, PORTABLE / "desktop" / "ui" / "matriz_v22" / "assets" / "index-aCoLBegj.js"))
        pairs.append((bundle, PORTABLE / "desktop" / "publish" / "ui" / "matriz_v22" / "assets" / "index-aCoLBegj.js"))
        pairs.append((bundle, ROOT / "desktop" / "publish" / "ui" / "matriz_v22" / "assets" / "index-aCoLBegj.js"))
    for src, dst in pairs:
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(str(dst))
    # homepage must be the original interface (matriz_v22/index.html) — never mesa-live.html
    for cfg in [
        ROOT / "desktop" / "config" / "desktop.json",
    ]:
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            app = data.setdefault("app", {})
            app["homepage"] = "https://aura.local/index.html"
            app["fallbackHomepages"] = ["https://aura.local/index.html"]
            cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            copied.append("homepage:" + str(cfg))
        except Exception:
            pass
    return copied


def start_one(title, script, args, url):
    st, _, _ = http("GET", url, timeout=2)
    if st == 200:
        return title + "=ja_ok"
    py = find_python()
    if not py:
        return title + "=sem_python"
    env = os.environ.copy()
    env["AURA_PAPER_ONLY"] = "1"
    env["AURA_EXECUTION_ALLOWED"] = "0"
    env["GLM_ADVISORY_ONLY"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "engine"), str(ROOT / "bridge")])
    env["PYTHONUNBUFFERED"] = "1"
    log_dir = LOCAL / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / ("matriz_%s.log" % title.lower()), "a", encoding="utf-8")
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
    subprocess.Popen(
        [str(py), "-u", str(ROOT / script), *args],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )
    for _ in range(40):
        time.sleep(1)
        st, _, _ = http("GET", url, timeout=2)
        if st == 200:
            return title + "=ok"
    return title + "=falhou"


def restart_desktop():
    exe = find_exe()
    if os.name == "nt":
        subprocess.run(["taskkill", "/IM", "Aura.QuantX.Desktop.exe", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        time.sleep(1)
    if not exe:
        return False, "EXE ausente — corre AURA_INSTALAR_TUDO_LIMPO.bat"
    if os.name == "nt":
        subprocess.Popen([str(exe)], cwd=str(ROOT), creationflags=0x00000008)
    return True, str(exe)



def tail(path: Path, n: int = 8) -> str:
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except Exception:
        return ""


def inspect_install():
    checks = {}
    checks["fonte_engine"] = (ROOT / "engine" / "server.py").exists()
    checks["fonte_mesa_live"] = (ROOT / "desktop" / "ui" / "matriz_v22" / "mesa-live.html").exists()
    checks["fonte_capture_stay"] = False
    cap = ROOT / "desktop" / "capture" / "aura-capture.js"
    if cap.exists():
        txt = cap.read_text(encoding="utf-8", errors="replace")
        checks["fonte_capture_stay"] = "stayInside" in txt or "__AURA_CAPTURE_V25T7__" in txt
    cfg = PORTABLE / "desktop" / "config" / "desktop.json"
    checks["portable_homepage_mesa"] = False
    if cfg.exists():
        try:
            home = (json.loads(cfg.read_text(encoding="utf-8")).get("app") or {}).get("homepage") or ""
            checks["portable_homepage_mesa"] = "mesa-live.html" in home
            checks["portable_homepage"] = home
        except Exception:
            checks["portable_homepage"] = "invalid_json"
    checks["portable_mesa_live"] = (PORTABLE / "desktop" / "ui" / "matriz_v22" / "mesa-live.html").exists() or (
        PORTABLE / "desktop" / "publish" / "ui" / "matriz_v22" / "mesa-live.html"
    ).exists()
    checks["exe"] = bool(find_exe())
    checks["venv_fonte"] = (ROOT / "engine" / "venv" / "Scripts" / "python.exe").exists()
    checks["venv_portable"] = (PORTABLE / "engine" / "venv" / "Scripts" / "python.exe").exists()
    return checks


def ask_glm(facts: dict) -> str:
    prompt = (
        "Advisor AURA QUANT-X paper-only. Nao invente placar nem fixture. "
        "Use so o JSON. Responda em PT em 5 linhas: "
        "MOTIVO / O QUE JA FOI CORRIGIDO / O QUE O HUMANO FAZ / RISCO / SE FALHAR.\n"
        + json.dumps(facts, ensure_ascii=False)[:1800]
    )
    st, body, _ = http("POST", ENGINE + "/api/trader/chat", {"message": prompt, "fixtureId": ""}, timeout=18)
    if st == 200 and isinstance(body, dict):
        for k in ("reply", "response", "text", "answer", "content"):
            if isinstance(body.get(k), str) and body[k].strip():
                return body[k].strip()
    st, body, _ = http(
        "POST",
        "http://127.0.0.1:11434/api/chat",
        {"model": os.environ.get("CORNERAI_CHAT_MODEL", "glm4:9b-chat-q4_0"), "stream": False,
         "messages": [{"role": "user", "content": prompt}]},
        timeout=20,
    )
    if st == 200 and isinstance(body, dict):
        msg = ((body.get("message") or {}).get("content")) or body.get("response")
        if msg:
            return str(msg).strip()
    return "GLM offline. A regra do boot ja classificou o corte. Nao e preciso modelo para seguir."

def view_of(state):
    if not isinstance(state, dict):
        return {}
    snap = state.get("snapshot") or {}
    return snap.get("view") or {}


def classify(bridge, engine, state):
    if engine != 200:
        return "ENGINE_DOWN", "Engine :8765 morto. Matriz cai em simulado."
    if bridge not in (200, 503):
        return "BRIDGE_DOWN", "Bridge :8080 morto. Captura nao entra."
    v = view_of(state)
    home = v.get("home") or (state or {}).get("home")
    away = v.get("away") or (state or {}).get("away")
    fid = (state or {}).get("fixtureId") or v.get("fixture_id")
    if home or fid:
        return "MATRIX_LIVE", "Engine tem jogo %s x %s. Matriz deve mostrar LIVE." % (home, away)
    return "NO_CAPTURE", "Nucleo no ar sem fixture. Abre um AO VIVO na pane direita do AURA."


def main():
    print("=" * 72)
    print(" AURA BOOT MATRIZ  |  diagnostico ponta a ponta")
    print(" Objectivo: inicializar Mesa live, nao o cartaz simulado.")
    print("=" * 72)
    print(" ROOT    ", ROOT)
    print(" PORTABLE", PORTABLE)
    print(" EXE     ", find_exe() or "AUSENTE")
    print(" PYTHON  ", find_python() or "AUSENTE")

    print("\n[1] Publicar assets da Matriz no portable")
    copied = copy_matrix_assets()
    print("     ficheiros:", len(copied))

    print("\n[2] Nucleo")
    b = start_one("Bridge", "bridge/server.py", ["--host", "127.0.0.1", "--port", "8080"], BRIDGE + "/health")
    e = start_one("Engine", "engine/server.py", ["--host", "127.0.0.1", "--port", "8765"], ENGINE + "/api/health")
    print("    ", b, "|", e)

    print("\n[3] Ler ui/state")
    st_u, body_u, err_u = http("GET", ENGINE + "/api/ui/state")
    v = view_of(body_u)
    print("     HTTP", st_u, "home=", v.get("home"), "away=", v.get("away"), "min=", v.get("minute"), err_u or "")

    st_b, _, _ = http("GET", BRIDGE + "/health")
    st_e, _, _ = http("GET", ENGINE + "/api/health")
    code, reason = classify(st_b, st_e, body_u if isinstance(body_u, dict) else {})
    print("\n[4] Instalacao / portable")
    inst = inspect_install()
    for k, val in inst.items():
        print("    ", k, "=", val)

    print("\n[5] DIAGNOSTICO MATRIZ:", code)
    print("    ", reason)

    facts = {
        "code": code,
        "reason": reason,
        "bridge": st_b,
        "engine": st_e,
        "ui_state": st_u,
        "home": v.get("home"),
        "away": v.get("away"),
        "install": inst,
        "capture_log": tail(LOCAL / "logs" / "capture_forwarder.log"),
        "desktop_log": tail(LOCAL / "logs" / "desktop_process.log"),
        "politica": "paper_only execution_allowed=false",
    }
    print("\n[6] GLM")
    glm = ask_glm(facts)
    print("   " + glm.replace("\n", "\n   ")[:900])

    print("\n[7] Reiniciar Desktop com homepage index.html (interface original V25Q)")
    ok, detail = restart_desktop()
    print("    ", ok, detail)

    print("\n" + "=" * 72)
    if code == "MATRIX_LIVE":
        print(" MATRIZ: dados no Engine. Confirma LIVE na pane esquerda.")
    elif code == "NO_CAPTURE":
        print(" MATRIZ: nucleo OK. UNICO clique: SokkerPRO a direita -> fixture AO VIVO.")
        print(" O placar tem de ficar na pane do AURA, nao no Opera.")
    elif code == "ENGINE_DOWN":
        print(" MATRIZ: sobe AURA_SUBIR_ENGINE_VISIVEL.bat e corre este tool outra vez.")
    else:
        print(" MATRIZ:", reason)
    print(" Relatorio em %LOCALAPPDATA%\\AURA_QUANT_X\\logs\\aura_matriz_boot.json")
    print("=" * 72)

    out = LOCAL / "logs" / "aura_matriz_boot.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "code": code,
            "reason": reason,
            "ui_state_http": st_u,
            "home": v.get("home"),
            "away": v.get("away"),
            "copied": copied[-12:],
            "exe": str(find_exe()) if find_exe() else None,
            "install": inst,
            "glm": glm,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return 0 if code in {"MATRIX_LIVE", "NO_CAPTURE"} else 1


if __name__ == "__main__":
    sys.exit(main())
