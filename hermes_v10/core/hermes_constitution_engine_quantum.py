#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constitution QUANTUM — attestation by critical-file hash (not hardware TPM)
+ case-insensitive pattern scan from v2.
"""
from __future__ import annotations
import hashlib, json, os, re, sys, time, unicodedata
from pathlib import Path
from typing import Any, List, Optional, Tuple

# reuse patterns from hardened config
class ZKConstitutionViolation(Exception):
    def __init__(self, rule: str, proof: str):
        self.rule = rule
        self.proof = proof
        super().__init__(f"ZK_CONSTITUTION [{rule}]: {proof}")

class ConstitutionZK:
    CRITICAL = [
        "hermes_config_ultra.json",
        "core/hermes_constitution_engine_quantum.py",
        "core/hermes_llm_engine.py",
        "security/hermes_integrity_guard.py",
    ]

    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.attestation_file = self.root / "security" / "boot_attestation.sha256"
        self.attestation_file.parent.mkdir(parents=True, exist_ok=True)
        self.forbidden_actions = {
            "set_execution_true", "enable_execution", "disable_paper_trade", "activate_live_orders"
        }
        flags = re.IGNORECASE
        self.patterns = [
            re.compile(p, flags) for p in [
                r"execution_allowed\s*=\s*['\"]?true['\"]?",
                r"allowRealOrders\s*:\s*['\"]?true['\"]?",
                r"paper_trade\s*=\s*['\"]?false['\"]?",
                r"aposta\s+real",
                r"ordem\s+real",
            ]
        ]
        self.log = self.root / "logs_ultra" / "constitution_zk.log"
        self.log.parent.mkdir(parents=True, exist_ok=True)

    def system_attestation(self) -> str:
        h = hashlib.sha256()
        for rel in self.CRITICAL:
            p = self.root / rel
            if p.exists():
                h.update(rel.encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    def verify_attestation(self, update_if_missing: bool = True) -> bool:
        current = self.system_attestation()
        if not self.attestation_file.exists():
            if update_if_missing:
                self.attestation_file.write_text(current, encoding="utf-8")
                return True
            return False
        saved = self.attestation_file.read_text(encoding="utf-8").strip()
        return current == saved

    def seal_attestation(self) -> str:
        current = self.system_attestation()
        self.attestation_file.write_text(current, encoding="utf-8")
        return current

    def _normalize(self, text: str) -> str:
        t = unicodedata.normalize("NFKC", text or "")
        t = re.sub(r'(["\'])\s*\+\s*(["\'])', "", t)
        return t

    def check_action_zk(self, action: str, payload: Any = None) -> None:
        if not self.verify_attestation():
            raise ZKConstitutionViolation("attestation_failed", "integrity/attestation mismatch — lockdown")
        if action in self.forbidden_actions:
            raise ZKConstitutionViolation("forbidden_action", action)
        blob = self._normalize(action + "\n" + json.dumps(payload, default=str, ensure_ascii=False))
        for i, pat in enumerate(self.patterns):
            m = pat.search(blob)
            if m:
                raise ZKConstitutionViolation("forbidden_pattern", f"{i}:{m.group(0)}")
        # force env
        if os.environ.get("EXECUTION_ALLOWED", "false").lower() in ("true", "1", "yes"):
            raise ZKConstitutionViolation("env", "EXECUTION_ALLOWED=true")
        os.environ["PAPER_TRADE"] = "true"
        os.environ["EXECUTION_ALLOWED"] = "false"

    def audit(self, event: str, detail: dict) -> None:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {event} {json.dumps(detail, ensure_ascii=False)}\n"
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(line)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "."))
    ap.add_argument("--seal", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    c = ConstitutionZK(args.root)
    if args.seal:
        print(json.dumps({"sealed": c.seal_attestation()}))
    if args.check:
        ok = c.verify_attestation(update_if_missing=False)
        print(json.dumps({"attestation_ok": ok}))
        try:
            c.check_action_zk("status", {})
            print(json.dumps({"action_status": "allowed"}))
            c.check_action_zk("set_execution_true", {})
        except ZKConstitutionViolation as e:
            print(json.dumps({"blocked": str(e)}))
