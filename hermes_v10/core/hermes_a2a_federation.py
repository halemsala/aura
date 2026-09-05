#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal A2A-style federation envelope (HMAC-like sha256 signature)."""
from __future__ import annotations
import hashlib, json, urllib.error, urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

@dataclass
class A2AEnvelope:
    protocol: str = "A2A/1.0"
    from_agent: str = ""
    to_agent: str = ""
    task_id: str = ""
    intent: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""

class A2AClient:
    def __init__(self, local_agent: str, remote_endpoints: Optional[Dict[str, str]] = None):
        self.local = local_agent
        self.endpoints = remote_endpoints or {}

    def _sign(self, env: A2AEnvelope, secret: str) -> str:
        msg = f"{env.from_agent}{env.to_agent}{env.task_id}{env.intent}"
        return hashlib.sha256((msg + secret).encode()).hexdigest()[:32]

    def delegate(self, remote_agent: str, intent: str, payload: dict, secret: str) -> dict:
        url = self.endpoints.get(remote_agent)
        if not url:
            return {"error": f"unknown remote agent {remote_agent}"}
        env = A2AEnvelope(
            from_agent=self.local, to_agent=remote_agent,
            task_id=hashlib.sha256(str(payload).encode()).hexdigest()[:16],
            intent=intent, payload=payload,
        )
        env.signature = self._sign(env, secret)
        data = json.dumps(asdict(env)).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-A2A-Protocol": "A2A/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def receive(self, envelope: dict, secret: str) -> dict:
        env = A2AEnvelope(**{k: envelope.get(k, getattr(A2AEnvelope(), k)) for k in (
            "protocol", "from_agent", "to_agent", "task_id", "intent", "payload", "signature"
        )})
        if env.signature != self._sign(env, secret):
            return {"error": "invalid_signature"}
        if env.to_agent != self.local:
            return {"error": "not_for_me"}
        return {"status": "accepted", "task_id": env.task_id, "intent": env.intent}

if __name__ == "__main__":
    c = A2AClient("hermes-local")
    env = A2AEnvelope(from_agent="a", to_agent="hermes-local", task_id="t1", intent="status", payload={})
    env.signature = c._sign(env, "secret")
    print(c.receive(asdict(env), "secret"))
