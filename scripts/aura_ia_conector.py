# -*- coding: utf-8 -*-
"""
AURA IA CONECTOR
- Mede send/recv no Bridge/Engine
- Classifica o corte (regra + GLM advisory)
- Executa SO as acoes da lista branca
- Nao inventa fixture real, nao liga extensao, nao opera dinheiro
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
ENGINE_CHAT = "http://127.0.0.1:8765/api/trader/chat"
OLLAMA_CHAT = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = os.environ.get("CORNERAI_CHAT_MODEL", "glm4:9b-chat-q4_0")
ALLOWED = {"COPY_CAPTURE", "START_SERVICES", "RESTART_DESKTOP", "EXPLAIN", "STOP"}


def http(method, url, payload=None, headers=None, timeout=5.0):
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
                body = {"raw": raw[:400]}
            return resp.status, body, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw[:400]}
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
    for p in [
        PORTABLE / "desktop" / "publish" / "Aura.QuantX.Desktop.exe",
        ROOT / "desktop" / "publish" / "Aura.QuantX.Desktop.exe",
    ]:
        if p.exists():
            return p
    return None


def capture_src():
    for p in [
        ROOT / "tools" / "ia_conector" / "aura-capture.js",
        ROOT / "desktop" / "capture" / "aura-capture.js",
        HERE / "aura-capture.js",
    ]:
        if p.exists():
            return p
    return None


def action_copy_capture():
    src = capture_src()
    if not src:
        return False, "aura-capture.js ausente"
    dests = [
        PORTABLE / "desktop" / "capture" / "aura-capture.js",
        PORTABLE / "desktop" / "publish" / "capture" / "aura-capture.js",
        ROOT / "desktop" / "capture" / "aura-capture.js",
        ROOT / "desktop" / "publish" / "capture" / "aura-capture.js",
    ]
    n = 0
    for d in dests:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d)
        n += 1
    return True, "copiado %s destinos" % n


def action_start_services():
    py = find_python()
    if not py:
        return False, "python/venv ausente"
    started = []
    for title, script, args, url in [
        ("Bridge", "bridge/server.py", ["--host", "127.0.0.1", "--port", "8080"], "http://127.0.0.1:8080/health"),
        ("Engine", "engine/server.py", ["--host", "127.0.0.1", "--port", "8765"], "http://127.0.0.1:8765/api/health"),
    ]:
        st, _, _ = http("GET", url, timeout=2)
        if st == 200:
            started.append(title + "=ja_ok")
            continue
        env = os.environ.copy()
        env["AURA_PAPER_ONLY"] = "1"
        env["AURA_EXECUTION_ALLOWED"] = "0"
        env["GLM_ADVISORY_ONLY"] = "1"
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "engine"), str(ROOT / "bridge")])
        log_dir = LOCAL / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log = open(log_dir / ("ia_%s.log" % title.lower()), "a", encoding="utf-8")
        flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
        subprocess.Popen(
            [str(py), str(ROOT / script), *args],
            cwd=str(ROOT),
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )
        ok = False
        for _ in range(35):
            time.sleep(1)
            st, _, _ = http("GET", url, timeout=2)
            if st == 200:
                ok = True
                break
        started.append("%s=%s" % (title, "ok" if ok else "falhou"))
    return True, ", ".join(started)


def action_restart_desktop():
    exe = find_exe()
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/IM", "Aura.QuantX.Desktop.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        time.sleep(1)
    if not exe:
        return False, "EXE nao encontrado"
    if os.name == "nt":
        subprocess.Popen([str(exe)], cwd=str(ROOT), creationflags=0x00000008)
    return True, str(exe)


def probe_once(n: int):
    tok = os.environ.get("CORNERAI_BRIDGE_TOKEN", "").strip()
    payload = {
        "schema": "cornerai-analyst-1",
        "source": "AURA_IA_PROBE",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "ts": int(time.time() * 1000),
        "fixture": {
            "id": "999000001",
            "league": "PROBE",
            "home": "PROBE_HOME",
            "away": "PROBE_AWAY",
            "minute": 11,
            "status": "probe",
            "score": {"home": 0, "away": 0},
        },
        "pressure": {"gauge": 50},
        "corners": {"total": {"home": 0, "away": 0}, "events": []},
        "quality": {"score": 0.1, "probe": True},
    }
    headers = {"X-CornerAI-Schema": "cornerai-analyst-1"}
    if tok:
        headers["X-CornerAI-Token"] = tok
    st_p, body_p, err_p = http("POST", "http://127.0.0.1:8080/api/cornerai/feed", payload, headers)
    st_u, body_u, err_u = http("GET", "http://127.0.0.1:8765/api/ui/state")
    view = {}
    if isinstance(body_u, dict):
        view = (body_u.get("snapshot") or {}).get("view") or {}
    home = view.get("home")
    got = home == "PROBE_HOME" or str(body_u.get("fixtureId") if isinstance(body_u, dict) else "") == "999000001"
    return {
        "n": n,
        "post": st_p,
        "post_err": err_p,
        "post_body": str(body_p)[:180],
        "state": st_u,
        "home": home,
        "away": view.get("away"),
        "minute": view.get("minute"),
        "probe_echo": got,
        "bridge": http("GET", "http://127.0.0.1:8080/health")[0],
        "engine": http("GET", "http://127.0.0.1:8765/api/health")[0],
    }


def classify(obs: dict) -> tuple[str, str]:
    if obs.get("bridge") != 200 or obs.get("engine") != 200:
        return "START_SERVICES", "Bridge/Engine sem health 200"
    if obs.get("post") == 401:
        return "EXPLAIN", "Bridge 401: token. Nucleo vive; captura Desktop usa token do proprio EXE. Nao e o popup."
    if obs.get("post") in (200, 201) and obs.get("probe_echo"):
        return "RESTART_DESKTOP", "Nucleo send/recv OK. Falta o jogo ficar no WebView2. Reinicia Desktop com script novo."
    if obs.get("post") in (200, 201) and not obs.get("probe_echo"):
        return "EXPLAIN", "POST aceite, ui/state sem PROBE. Engine nao publicou view de teste."
    if obs.get("post") is None:
        return "START_SERVICES", "POST feed sem conexao"
    return "EXPLAIN", "Estado inconclusivo: POST=%s STATE=%s" % (obs.get("post"), obs.get("state"))


def ask_glm(obs: dict, action: str, reason: str) -> str:
    prompt = (
        "Advisor AURA QUANT-X paper-only. Nao invente jogo real. "
        "JSON=%s ACTION=%s REASON=%s "
        "Responda 4 linhas: MOTIVO / ACAO / O QUE O HUMANO CLICA / SE FALHAR."
        % (json.dumps(obs, ensure_ascii=False)[:1200], action, reason)
    )
    st, body, _ = http("POST", ENGINE_CHAT, {"message": prompt, "fixtureId": ""}, timeout=15)
    if st == 200 and isinstance(body, dict):
        for k in ("reply", "response", "text", "answer", "content"):
            if isinstance(body.get(k), str) and body[k].strip():
                return body[k].strip()
    st, body, _ = http(
        "POST",
        OLLAMA_CHAT,
        {"model": OLLAMA_MODEL, "stream": False, "messages": [{"role": "user", "content": prompt}]},
        timeout=20,
    )
    if st == 200 and isinstance(body, dict):
        msg = (body.get("message") or {}).get("content") or body.get("response")
        if msg:
            return str(msg).strip()
    return "(GLM offline — a classificacao por regra ja escolheu a acao)"


def run_action(name: str) -> tuple[bool, str]:
    if name == "COPY_CAPTURE":
        return action_copy_capture()
    if name == "START_SERVICES":
        return action_start_services()
    if name == "RESTART_DESKTOP":
        return action_restart_desktop()
    if name == "EXPLAIN":
        return True, "sem mutacao extra"
    if name == "STOP":
        return True, "stop"
    return False, "acao fora da lista branca"


def main() -> int:
    print("=" * 72)
    print(" AURA IA CONECTOR  |  paper-only  |  lista branca de acoes")
    print("=" * 72)
    print(" ROOT =", ROOT)
    ok, msg = action_copy_capture()
    print(" [BOOT] COPY_CAPTURE:", ok, msg)

    history = []
    last_action = None
    for i in range(1, 5):
        print("\n--- ciclo %s ---" % i)
        obs = probe_once(i)
        print("  health B/E=%s/%s POST=%s echo=%s home=%r" % (
            obs.get("bridge"), obs.get("engine"), obs.get("post"), obs.get("probe_echo"), obs.get("home")))
        action, reason = classify(obs)
        if i == 1 and action != "START_SERVICES":
            # sempre garante o script no primeiro ciclo
            run_action("COPY_CAPTURE")
        if action == last_action == "EXPLAIN":
            action = "STOP"
        print("  REGRA ->", action, "|", reason)
        glm = ask_glm(obs, action, reason)
        print("  GLM:\n   " + glm.replace("\n", "\n   ")[:800])
        if action in ALLOWED:
            ok, detail = run_action(action)
            print("  EXEC", action, ok, detail)
        history.append({"obs": obs, "action": action, "reason": reason, "glm": glm})
        last_action = action
        if action == "STOP":
            break
        time.sleep(1.2)

    print("\n" + "=" * 72)
    print(" HUMANO (unico clique que a IA nao deve forjar):")
    print("  Na janela AURA -> SokkerPRO -> UM jogo AO VIVO")
    print("  Placar DEBAIXO da toolbar. Rodape ok > 0 -> Operator")
    print("  Se o fixture abrir no Opera, o script novo falhou o intercept.")
    print("=" * 72)
    out = LOCAL / "logs" / "aura_ia_conector.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        print(" Relatorio:", out)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
