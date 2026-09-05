"""AURA helper: Ollama REST client (generate/chat/stream) with basic error handling.
Uses only stdlib. Optional: pip install ollama for official client.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional

DEFAULT_BASE = "http://127.0.0.1:11434"


class OllamaRestError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def _request(method: str, url: str, payload: Optional[dict] = None, timeout: float = 120.0):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise OllamaRestError(f"HTTP {e.code}: {body[:300]}", status=e.code, body=body) from e
    except urllib.error.URLError as e:
        raise OllamaRestError(f"URL error: {e.reason}") from e


def list_models(base: str = DEFAULT_BASE) -> Dict[str, Any]:
    _, text = _request("GET", f"{base.rstrip('/')}/api/tags", timeout=10)
    return json.loads(text)


def generate(model: str, prompt: str, base: str = DEFAULT_BASE, stream: bool = False) -> Any:
    payload = {"model": model, "prompt": prompt, "stream": stream}
    if not stream:
        _, text = _request("POST", f"{base.rstrip('/')}/api/generate", payload)
        return json.loads(text)
    return _stream_post(f"{base.rstrip('/')}/api/generate", payload)


def chat(model: str, message: str, base: str = DEFAULT_BASE, stream: bool = False) -> Any:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "stream": stream,
    }
    if not stream:
        _, text = _request("POST", f"{base.rstrip('/')}/api/chat", payload)
        return json.loads(text)
    return _stream_post(f"{base.rstrip('/')}/api/chat", payload)


def _stream_post(url: str, payload: dict) -> Iterator[dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"}, method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise OllamaRestError(f"stream HTTP {e.code}: {body[:300]}", status=e.code, body=body) from e
    except urllib.error.URLError as e:
        raise OllamaRestError(f"stream URL error: {e.reason}") from e

    def _gen() -> Iterator[dict]:
        try:
            while True:
                line = resp.readline()
                if not line:
                    break
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as je:
                    raise OllamaRestError(f"bad stream JSON: {line[:200]}") from je
                if obj.get("error"):
                    raise OllamaRestError(str(obj["error"]))
                yield obj
                if obj.get("done") is True:
                    break
        finally:
            resp.close()

    return _gen()


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="AURA Ollama REST helper")
    p.add_argument("--base", default=DEFAULT_BASE)
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--prompt", default="Diz apenas: OK REST")
    p.add_argument("--stream", action="store_true")
    p.add_argument("--mode", choices=["tags", "generate", "chat"], default="chat")
    args = p.parse_args(argv)
    try:
        if args.mode == "tags":
            print(json.dumps(list_models(args.base), ensure_ascii=False, indent=2))
            return 0
        if args.mode == "generate":
            if args.stream:
                for chunk in generate(args.model, args.prompt, args.base, stream=True):
                    sys.stdout.write(chunk.get("response") or "")
                    sys.stdout.flush()
                print()
            else:
                r = generate(args.model, args.prompt, args.base, stream=False)
                print(r.get("response", r))
            return 0
        # chat
        if args.stream:
            for chunk in chat(args.model, args.prompt, args.base, stream=True):
                msg = chunk.get("message") or {}
                sys.stdout.write(msg.get("content") or chunk.get("response") or "")
                sys.stdout.flush()
            print()
        else:
            r = chat(args.model, args.prompt, args.base, stream=False)
            print((r.get("message") or {}).get("content", r))
        return 0
    except OllamaRestError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        if e.status:
            print(f"status={e.status}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
