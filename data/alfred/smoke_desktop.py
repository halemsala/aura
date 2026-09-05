import requests
urls = [
    ("alfred", "http://127.0.0.1:8791/health"),
    ("hermes", "http://127.0.0.1:8777/health"),
    ("matriz_health", "http://127.0.0.1:8766/health"),
    ("matriz_root", "http://127.0.0.1:8766/"),
    ("ops", "http://127.0.0.1:8766/ops_status.json"),
    ("agents", "http://127.0.0.1:8766/api/aura/agents"),
    ("agents2", "http://127.0.0.1:8765/api/aura/agents"),
    ("bridge", "http://127.0.0.1:8080/health"),
    ("engine", "http://127.0.0.1:8765/api/health"),
]
for n, u in urls:
    try:
        r = requests.get(u, timeout=4)
        print(n, r.status_code, r.text[:240].replace("\n", " "))
    except Exception as e:
        print(n, "DOWN", type(e).__name__, str(e)[:120])

print("---deps---")
try:
    import cv2
    print("cv2", cv2.__version__)
except Exception as e:
    print("cv2 MISSING", e)
try:
    from PIL import ImageGrab
    print("PIL OK")
except Exception as e:
    print("PIL MISSING", e)
