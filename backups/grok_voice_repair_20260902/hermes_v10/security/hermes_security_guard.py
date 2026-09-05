#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes V10 Security Guard — paper-trade enforcement + integrity baseline."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path
from typing import Dict, Optional

class HermesSecurityGuard:
    def __init__(self, root: str, config_path: Optional[str] = None):
        self.root = Path(root).resolve()
        self.config = self._load_config(config_path)
        sec = self.config.get("security", {})
        self.audit_log = self.root / sec.get("audit_log", "logs_supervisor/security_audit.log")
        self.allowed_hashes_file = self.root / sec.get("allowed_hashes_file", "security/allowed_hashes.sha256")
        self.max_failed = int(sec.get("max_failed_checks", 5))
        self.block_on_failure = bool(sec.get("block_on_failure", False))
        self.failed_checks = 0
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.allowed_hashes_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_config(self, path: Optional[str]) -> dict:
        for p in [path, self.root / "hermes_config.json", self.root / "hermes_v10" / "hermes_config.json"]:
            if p and Path(p).exists():
                return json.loads(Path(p).read_text(encoding="utf-8"))
        return {}

    def _log(self, level: str, message: str) -> None:
        entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] SECURITY: {message}"
        print(entry)
        try:
            with open(self.audit_log, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def compute_hash(self, filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _critical_files(self):
        return [
            "scripts/hermes_v10_chat_api.py",
            "scripts/hermes_v9_chat_api.py",
            "engine/agents/hermes_agents_v9_max.py",
            "scripts/hermes_deep_diagnostic.py",
            "hermes_config.json",
        ]

    def _create_baseline(self) -> Dict[str, str]:
        hashes = {}
        lines = [f"# Hermes V10 baseline {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
        for rel in self._critical_files():
            full = self.root / rel
            if not full.exists():
                # try under hermes_v10 subfolder layout
                full = self.root / "hermes_v10" / rel if (self.root / "hermes_v10" / rel).exists() else full
            if full.exists():
                file_hash = self.compute_hash(full)
                hashes[rel] = file_hash
                lines.append(f"{file_hash}  {rel}\n")
                self._log("INFO", f"baseline {rel}: {file_hash[:16]}...")
        self.allowed_hashes_file.write_text("".join(lines), encoding="utf-8")
        return hashes

    def load_allowed_hashes(self) -> Dict[str, str]:
        if not self.allowed_hashes_file.exists():
            return self._create_baseline()
        hashes = {}
        for line in self.allowed_hashes_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                hashes[parts[1]] = parts[0]
        return hashes

    def verify_integrity(self) -> bool:
        allowed = self.load_allowed_hashes()
        all_ok = True
        for rel, expected in allowed.items():
            full = self.root / rel
            if not full.exists():
                full = self.root / "hermes_v10" / rel
            if not full.exists():
                self._log("WARN", f"ausente: {rel}")
                continue
            actual = self.compute_hash(full)
            if actual != expected:
                self._log("CRITICAL", f"integridade: {rel}")
                all_ok = False
                self.failed_checks += 1
            else:
                self._log("INFO", f"OK {rel}")
        if self.failed_checks >= self.max_failed and self.block_on_failure:
            self._log("CRITICAL", "BLOQUEIO por falhas de integridade")
            return False
        return all_ok

    def check_environment_safety(self) -> bool:
        ex = os.environ.get("EXECUTION_ALLOWED", "false").lower()
        pt = os.environ.get("PAPER_TRADE", "true").lower()
        if ex not in ("false", "0", "no", ""):
            self._log("CRITICAL", "EXECUTION_ALLOWED != false — bloqueado")
            return False
        if pt not in ("true", "1", "yes", ""):
            self._log("WARN", "forçar PAPER_TRADE=true")
            os.environ["PAPER_TRADE"] = "true"
        os.environ["EXECUTION_ALLOWED"] = "false"
        os.environ["PAPER_TRADE"] = "true"
        self._log("INFO", "ambiente OK paper_trade=true execution_allowed=false")
        return True

    def run(self, mode: str = "check") -> int:
        if mode == "baseline":
            self._create_baseline()
            return 0
        ok1 = self.check_environment_safety()
        ok2 = self.verify_integrity()
        if ok1 and ok2:
            self._log("INFO", "Security check PASSED")
            return 0
        self._log("WARN", "Security check com avisos/falhas")
        return 0 if not self.block_on_failure else 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["check", "baseline"], default="check")
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    sys.exit(HermesSecurityGuard(args.root, args.config).run(args.mode))
