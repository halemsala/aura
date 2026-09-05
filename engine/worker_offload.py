"""Cliente opcional de offload advisory para Workers privados.

O cliente é opt-in, usa Bearer token, limita tamanho de contexto e nunca
trata resposta remota como autorização. Quando um peer falha, tenta o próximo
peer configurado e, se todos falharem, o chamador continua pela inferência
local do runtime atual.
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_TRUE = {"1", "true", "yes", "on"}
_MAX_PEERS = 8


def _enabled() -> bool:
    return os.getenv("AURA_WORKER_OFFLOAD_ENABLED", "false").strip().lower() in _TRUE


def _safe_timeout() -> float:
    try:
        return max(1.0, min(float(os.getenv("AURA_WORKER_TIMEOUT", "20")), 120.0))
    except (TypeError, ValueError):
        return 20.0


def _normalise_endpoint(value: str) -> str | None:
    endpoint = value.strip().rstrip("/")
    if not endpoint:
        return None
    try:
        parsed = urllib.parse.urlsplit(endpoint)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    if parsed.port is not None and not 1024 <= parsed.port <= 65535:
        return None
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None:
        tailnet_range = ipaddress.ip_network("100.64.0.0/10")
        allowed_private = address.is_private or address.is_loopback or address.is_link_local or address in tailnet_range
        if address.is_global and not allowed_private and os.getenv("AURA_WORKER_ALLOW_PUBLIC_ENDPOINT", "false").strip().lower() not in _TRUE:
            return None
    return endpoint


def _endpoint_label(endpoint: str) -> str:
    parsed = urllib.parse.urlsplit(endpoint)
    host = parsed.hostname or "unknown"
    return f"{host}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


class WorkerOffloadClient:
    def __init__(self) -> None:
        self.enabled = _enabled()
        raw_endpoints = os.getenv("AURA_WORKER_ENDPOINTS", "") or os.getenv("AURA_WORKER_ENDPOINT", "http://127.0.0.1:9999")
        self.endpoints = []
        for item in raw_endpoints.split(","):
            endpoint = _normalise_endpoint(item)
            if endpoint and endpoint not in self.endpoints:
                self.endpoints.append(endpoint)
            if len(self.endpoints) >= _MAX_PEERS:
                break
        self.token = os.getenv("AURA_WORKER_TOKEN", "").strip()
        self.tokens_by_endpoint: dict[str, str] = {}
        for item in os.getenv("AURA_WORKER_TOKENS", "").split(";"):
            if "=" not in item:
                continue
            endpoint_raw, token = item.split("=", 1)
            endpoint = _normalise_endpoint(endpoint_raw)
            if endpoint and token.strip():
                self.tokens_by_endpoint[endpoint] = token.strip()
        self.timeout_s = _safe_timeout()
        configured = os.getenv("AURA_WORKER_OFFLOAD_AGENTS", "WATCHDOG,AUTO_EVOLVER,MEMORY_CACHE")
        self.allowed_agents = {item.strip() for item in configured.split(",") if item.strip()}
        self.max_prompt_chars = 8_000
        self._cursor = 0
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.endpoints and (self.token or self.tokens_by_endpoint)),
            "peer_count": len(self.endpoints),
            "peers": [_endpoint_label(item) for item in self.endpoints],
            "timeout_s": self.timeout_s,
            "allowed_agents": sorted(self.allowed_agents),
            "mode": "ADVISORY_ONLY",
            "selection": "ROUND_ROBIN_FAILOVER",
            "fallback": "LOCAL_AGENT_GLM_RUNTIME",
            "execution_allowed": False,
            "paper_trade_only": True,
        }

    def eligible(self, agent: str) -> bool:
        return self.enabled and bool(self.endpoints) and str(agent or "") in self.allowed_agents and bool(self.token or self.tokens_by_endpoint)

    def _candidate_endpoints(self) -> list[str]:
        if not self.endpoints:
            return []
        with self._lock:
            start = self._cursor % len(self.endpoints)
            self._cursor = (self._cursor + 1) % len(self.endpoints)
        return self.endpoints[start:] + self.endpoints[:start]

    def _token_for(self, endpoint: str) -> str:
        return self.tokens_by_endpoint.get(endpoint, self.token)

    def process(self, agent: str, task_id: str, prompt: str) -> dict[str, Any] | None:
        if not self.eligible(agent):
            return None
        for endpoint in self._candidate_endpoints():
            token = self._token_for(endpoint)
            if not token:
                continue
            body = json.dumps({"task_id": str(task_id)[:160], "prompt": str(prompt)[:self.max_prompt_chars]}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                f"{endpoint}/process_advisory",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}", "User-Agent": "AURA-Worker-Offload/1.0"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
                if isinstance(payload, dict) and payload.get("ok") and isinstance(payload.get("result"), str) and payload["result"].strip():
                    return {"ok": True, "status": "ADVISORY_READY", "peer": _endpoint_label(endpoint), "gpu": payload.get("gpu") if isinstance(payload.get("gpu"), dict) else {"available": False, "backend": "unknown"}, "text": payload["result"].strip()[:4_000], "model": f"worker:{payload.get('model', 'unknown')}", "execution_allowed": False, "paper_trade_only": True}
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
                continue
            except Exception:
                continue
        return None


WORKER_OFFLOAD = WorkerOffloadClient()

__all__ = ["WorkerOffloadClient", "WORKER_OFFLOAD"]
