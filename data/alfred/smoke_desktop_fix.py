# -*- coding: utf-8 -*-
import json
import sys
import traceback

import requests

import alfred.tools  # noqa: F401  # registra open_app / capture_camera
from alfred.router import CAMERA_RE, TOOLS_LIST_RE, chunk_to_tasks, is_system_control, _bare

fails = []


def check(name, cond, detail=""):
    if cond:
        print("PASS", name, detail)
    else:
        print("FAIL", name, detail)
        fails.append(name)


# Router
check("camera ligue", bool(CAMERA_RE.match(_bare("LIGUE A CAMERA"))))
check("camera windows", bool(CAMERA_RE.match(_bare("consegue ligar a camera do windows"))))
check("sysctrl camera", is_system_control("ligue a camera"))
check("sysctrl o que", is_system_control("O QUE CONSEGUE FAZER?"))
tasks = chunk_to_tasks("ligue a camera") or []
check("chunk camera", tasks and tasks[0].tool == "open_app")
tasks = chunk_to_tasks("o que consegue fazer?") or []
check("chunk tools", tasks and tasks[0].tool == "list_tools")

base = "http://127.0.0.1:8766"
try:
    r = requests.get(base + "/health", timeout=5)
    check("matriz health", r.status_code == 200 and r.json().get("ok") is True, r.text[:80])
except Exception as e:
    check("matriz health", False, str(e))

r = requests.get(base + "/index.html", timeout=5, allow_redirects=False)
check("index redirect", r.status_code in (301, 302) and r.headers.get("Location", "").startswith("/"), r.headers.get("Location"))

r = requests.get(base + "/", timeout=5)
check("root html", r.status_code == 200 and "<!doctype html>" in r.text.lower()[:80])

r = requests.get(base + "/agentes", timeout=5)
check("spa agentes", r.status_code == 200 and "<!doctype html>" in r.text.lower()[:80], str(r.status_code))

r = requests.get(base + "/api/trpc/alertCenter.list?batch=1&input=%7B%220%22%3A%7B%22json%22%3A%7B%7D%7D%7D", timeout=5)
try:
    data = r.json()
except Exception:
    data = None
check("trpc batch array", r.status_code == 200 and isinstance(data, list) and isinstance(data[0]["result"]["data"]["json"], list), str(data)[:160])

r = requests.get(base + "/api/trpc/alertCenter.list", timeout=5)
data = r.json()
check("trpc unbatched array", isinstance(data.get("result", {}).get("data", {}).get("json"), list), str(data)[:120])

r = requests.get(base + "/api/aura/tools", timeout=8)
check("tools get", r.status_code == 200 and isinstance(r.json().get("tools"), list), f"{r.status_code} {r.text[:80]}")

r = requests.post(base + "/api/aura/tools/probe-all", json={}, timeout=8)
check("probe-all", r.status_code == 200 and r.json().get("ok") is True, f"{r.status_code} {r.text[:120]}")

r = requests.get(base + "/manus-storage/aura-quant-x-mark_b5517fbd.png", timeout=5)
check("manus placeholder", r.status_code == 200 and "svg" in (r.headers.get("Content-Type") or ""), f"{r.status_code} {r.headers.get('Content-Type')}")

r = requests.get(base + "/api/aura/agents", timeout=8)
js = r.json()
check("agents object", r.status_code == 200 and isinstance(js, dict) and "agents" in js, type(js).__name__)

for port, path in ((8791, "/health"), (8777, "/health"), (8765, "/api/health"), (8080, "/health"), (11434, "/api/tags")):
    try:
        rr = requests.get(f"http://127.0.0.1:{port}{path}", timeout=4)
        check(f"port {port}", rr.status_code == 200, str(rr.status_code))
    except Exception as e:
        check(f"port {port}", False, type(e).__name__)

# Hermes routes
try:
    r = requests.post("http://127.0.0.1:8777/api/chat", json={"message": "o que consegue fazer?", "use_memory": False}, timeout=25)
    body = r.json()
    reply = str(body.get("reply") or "")
    model = str(body.get("model") or "")
    check("hermes capabilities alfred", "alfred" in model.lower() or "list_tools" in reply.lower() or "ferramenta" in reply.lower(), f"model={model} reply={reply[:180]}")
except Exception as e:
    check("hermes capabilities alfred", False, str(e))

try:
    r = requests.post("http://127.0.0.1:8777/api/chat", json={"message": "ative todos agentes", "use_memory": False}, timeout=25)
    body = r.json()
    reply = str(body.get("reply") or "")
    check("ative todos not llm-refuse", "comando n" not in reply.lower() or "ativ" in reply.lower(), reply[:200])
except Exception as e:
    check("ative todos not llm-refuse", False, str(e))

print("FAILS", len(fails), fails)
sys.exit(1 if fails else 0)
