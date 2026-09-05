import json, urllib.request, socket, sys

def port_open(p):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", p))
        s.close()
        return True
    except Exception:
        return False

def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8", "replace")[:500]
    except Exception as e:
        return None, str(e)

print("=== AURA STACK CHECK ===")
for p, name in [(8080,"Bridge"),(8765,"Engine"),(8099,"Voice"),(11434,"Ollama"),(3000,"Dashboard")]:
    print(f"{name:10} :{'LISTEN' if port_open(p) else 'FECHADA':>8}  :{p}")

for url, name in [
    ("http://127.0.0.1:8099/api/voice/health", "VoiceHealth"),
    ("http://127.0.0.1:8765/api/health", "EngineHealth"),
    ("http://127.0.0.1:8080/health", "BridgeHealth"),
]:
    st, body = get(url)
    print(f"{name}: status={st}")
    if st and "voice" in url:
        try:
            j = json.loads(body)
            print(f"  engineReady={j.get('engineReady')} error={j.get('error')} device={j.get('device')}")
        except Exception:
            print(f"  body={body[:200]}")
