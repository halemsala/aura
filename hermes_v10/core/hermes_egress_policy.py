#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Egress allowlist + short-lived credential tokens (local)."""
from __future__ import annotations
import ipaddress, secrets, time
from dataclasses import dataclass
from typing import List

@dataclass
class EgressRule:
    pattern: str
    ports: List[int]
    protocol: str
    action: str

DEFAULT_POLICY = [
    EgressRule("127.0.0.0/8", [53, 11434, 8777, 8778, 8080, 8765, 8766], "tcp", "ALLOW"),
    EgressRule("api.openai.com", [443], "tcp", "ALLOW"),
    EgressRule("api.x.ai", [443], "tcp", "ALLOW"),
    EgressRule("0.0.0.0/0", [], "any", "DENY"),
]

class EgressGuard:
    def __init__(self, rules: List[EgressRule] | None = None):
        self.rules = rules or DEFAULT_POLICY

    def check(self, host: str, port: int, protocol: str = "tcp") -> bool:
        for rule in self.rules:
            if self._match(rule.pattern, host) and (not rule.ports or port in rule.ports or rule.protocol == "any"):
                return rule.action == "ALLOW"
        return False

    @staticmethod
    def _match(pattern: str, host: str) -> bool:
        if "/" in pattern:
            try:
                return ipaddress.ip_address(host) in ipaddress.ip_network(pattern, strict=False)
            except ValueError:
                return False
        if pattern.startswith("*."):
            return host.endswith(pattern[1:]) or host == pattern[2:]
        return host == pattern

class CredentialBroker:
    def __init__(self, secrets_store: dict | None = None):
        self._store = secrets_store or {}

    def issue_short_lived(self, service: str, ttl_seconds: int = 300) -> str:
        token = secrets.token_urlsafe(24)
        return f"slt_{service}_{token[:16]}_{int(time.time()) + ttl_seconds}"

if __name__ == "__main__":
    g = EgressGuard()
    print("localhost ollama", g.check("127.0.0.1", 11434))
    print("evil", g.check("evil.example", 443))
