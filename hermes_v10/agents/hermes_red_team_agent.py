#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Red Team — testes locais seguros (não ataca rede externa)."""
from __future__ import annotations
import argparse, json, os, re
from pathlib import Path
from typing import List

class RedTeamAgent:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.findings = []

    def scan(self) -> List[dict]:
        findings = []
        # 1) execution_allowed leakage in configs
        for pattern in ("**/*.json", "**/*.py", "**/*.txt", "**/*.bat"):
            for f in self.root.glob(pattern):
                if not f.is_file() or f.stat().st_size > 2_000_000:
                    continue
                try:
                    t = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if re.search(r"execution_allowed\s*=\s*true", t, re.I):
                    findings.append({
                        "vector": "config_injection",
                        "success": True,
                        "target": str(f.relative_to(self.root)),
                        "severity": "critical",
                        "evidence": "execution_allowed=true encontrado",
                        "recommendation": "forçar false + security guard",
                    })
                if re.search(r"allowRealOrders\s*[:=]\s*true", t, re.I):
                    findings.append({
                        "vector": "privilege_escalation",
                        "success": True,
                        "target": str(f.relative_to(self.root)),
                        "severity": "critical",
                        "evidence": "allowRealOrders true",
                        "recommendation": "bloquear no desktop.json",
                    })
        # 2) missing token path awareness
        token = Path(os.environ.get("LOCALAPPDATA", "")) / "AURA_QUANT_X" / "secure" / "cornerai_bridge_token.bin"
        if os.name == "nt" and not token.exists():
            findings.append({
                "vector": "capture_bypass",
                "success": True,
                "target": "bridge_token",
                "severity": "medium",
                "evidence": "token bridge ausente → fallback demonstrativo",
                "recommendation": "prepare_bridge_token.ps1 -Mode Ensure + Desktop",
            })
        self.findings = findings
        return findings

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    r = RedTeamAgent(ap.parse_args().root).scan()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"findings={len(r)}")
