#!/usr/bin/env python3
"""
AURA QUANT-X — Post-start smoke test
Validates Bridge :8080, Engine :8765, Voice :8099 before declaring system healthy.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

ENDPOINTS = [
    ("Bridge", "http://127.0.0.1:8080/health"),
    ("Engine", "http://127.0.0.1:8765/api/health"),
    ("Voice", "http://127.0.0.1:8099/api/voice/health"),
]
MAX_RETRIES = 10
RETRY_SEC = 3
MAX_LATENCY_MS = 200.0


def probe(url: str) -> tuple[bool, float, dict | None]:
    start = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AuraQuantX-Smoke/V25"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            latency_ms = (time.perf_counter() - start) * 1000
            body = resp.read().decode(errors="replace")
            data = None
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                pass
            return resp.getcode() == 200, latency_ms, data
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, (time.perf_counter() - start) * 1000, None


def run() -> bool:
    print("AURA QUANT-X smoke test — Bridge / Engine / Voice")
    all_ok = True
    for name, url in ENDPOINTS:
        ok = False
        for attempt in range(1, MAX_RETRIES + 1):
            success, latency, data = probe(url)
            if success:
                if latency > MAX_LATENCY_MS:
                    print(f"[FAIL] {name} latency {latency:.0f} ms > {MAX_LATENCY_MS} ms")
                    all_ok = False
                else:
                    extra = ""
                    if isinstance(data, dict):
                        pt = data.get("paper_trade")
                        ea = data.get("execution_allowed")
                        if pt is not None or ea is not None:
                            extra = f" | paper_trade={pt} execution_allowed={ea}"
                    print(f"[PASS] {name} HTTP 200 | {latency:.0f} ms{extra}")
                ok = True
                break
            print(f"[WAIT] {name} attempt {attempt}/{MAX_RETRIES} failed")
            time.sleep(RETRY_SEC)
        if not ok:
            print(f"[FAIL] {name} unreachable after {MAX_RETRIES} attempts")
            all_ok = False
    if all_ok:
        print("[SUCCESS] All services healthy. Invariants must remain paper_trade=true, execution_allowed=false.")
    else:
        print("[FAIL] Smoke test failed. Do not consider deploy complete.")
    return all_ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
