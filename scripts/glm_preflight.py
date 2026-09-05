#!/usr/bin/env python3
"""Read-only GLM/Ollama capability preflight for AURA Quant-X.

The script never installs, pulls, stops or mutates a model. It reports JSON and
returns 0 only when the Ollama endpoint is reachable and a configured model is
listed. Use --probe-chat only when a minimal inference call is authorized.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "glm4:9b-chat-q4_0"
MAX_TIMEOUT_S = 300.0


def _finite_timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout must be a finite number")
    try:
        timeout = float(value)
    except (OverflowError, ValueError):
        raise ValueError("timeout must be a finite number") from None
    if not math.isfinite(timeout) or not 0 < timeout <= MAX_TIMEOUT_S:
        raise ValueError("timeout must be positive, finite and at most 300 seconds")
    return timeout


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
        }
        if self.evidence:
            result["evidence"] = self.evidence
        return result


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "unknown-host"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme or 'http'}://{host}{port}"


def request_json(url: str, payload: dict[str, Any] | None, timeout: float) -> tuple[int, Any]:
    timeout = _finite_timeout(timeout)
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return response.status, json.loads(raw)


def run(base_url: str, model: str, timeout: float, probe_chat: bool) -> tuple[list[Check], int]:
    try:
        timeout = _finite_timeout(timeout)
    except ValueError as exc:
        return [Check("timeout", "BLOCKED", str(exc))], 1
    base = base_url.rstrip("/")
    checks: list[Check] = []
    checks.append(Check("endpoint", "INFO", safe_url(base)))

    try:
        status, payload = request_json(f"{base}/api/tags", None, timeout)
        if status != 200 or not isinstance(payload, dict):
            checks.append(Check("ollama_tags", "BLOCKED", f"unexpected HTTP/payload: {status}"))
            return checks, 1
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        checks.append(Check("ollama_tags", "BLOCKED", f"endpoint unavailable: {type(exc).__name__}"))
        return checks, 1

    raw_models = payload.get("models", [])
    names = [item.get("name") for item in raw_models if isinstance(item, dict) and item.get("name")]
    model_found = model in names
    checks.append(
        Check(
            "model_presence",
            "PASS" if model_found else "BLOCKED",
            f"configured model {'present' if model_found else 'missing'}",
            {"model": model, "installed_models": names},
        )
    )
    if not model_found:
        return checks, 1

    if probe_chat:
        request_payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Responda apenas GLM_PING."}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 8},
        }
        started = time.perf_counter()
        try:
            status, response = request_json(f"{base}/api/chat", request_payload, timeout)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            message = response.get("message", {}) if isinstance(response, dict) else {}
            content = message.get("content") if isinstance(message, dict) else None
            ok = status == 200 and isinstance(content, str) and bool(content.strip())
            checks.append(
                Check(
                    "chat_probe",
                    "PASS" if ok else "BLOCKED",
                    "minimal inference returned content" if ok else "minimal inference returned no valid content",
                    {"model": model, "latency_ms": elapsed_ms, "content_length": len(content or "")},
                )
            )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            checks.append(Check("chat_probe", "BLOCKED", f"probe failed: {type(exc).__name__}"))

    blocking = [item for item in checks if item.status == "BLOCKED"]
    return checks, 1 if blocking else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("AURA_OLLAMA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--model", default=os.getenv("AURA_GLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--probe-chat", action="store_true", help="run one minimal chat request; never writes externally")
    args = parser.parse_args()
    try:
        timeout = _finite_timeout(args.timeout)
    except ValueError:
        parser.error("--timeout must be positive, finite and at most 300 seconds; --model cannot be empty")
    if not args.model.strip():
        parser.error("--timeout must be positive, finite and at most 300 seconds; --model cannot be empty")
    checks, rc = run(args.base_url, args.model.strip(), timeout, args.probe_chat)
    print(json.dumps({"ok": rc == 0, "checks": [item.as_dict() for item in checks]}, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
