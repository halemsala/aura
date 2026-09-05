#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes V10 Correction Agent — allowlist + backup automático."""
from __future__ import annotations
import argparse, json, os, shutil, time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class CorrectionResult:
    success: bool
    fix_name: str
    backup_path: Optional[str] = None
    message: str = ""

class CorrectionAgent:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.backup_dir = self.root / "backups" / "auto_corrections"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        cfg = self.root / "hermes_config.json"
        self.config = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        self.allowlist = set(self.config.get("agents", {}).get("fix_allowlist", [
            "domain_lock", "fix_desktop_json", "set_execution_false", "rotate_logs"
        ]))

    def _backup(self, target: Path) -> Optional[Path]:
        if not target.exists():
            return None
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"{target.name}.{ts}.bak"
        if target.is_file():
            shutil.copy2(target, dest)
        return dest

    def apply(self, fix_name: str) -> CorrectionResult:
        if fix_name not in self.allowlist:
            return CorrectionResult(False, fix_name, message=f"não está na allowlist: {fix_name}")
        if fix_name == "domain_lock":
            p = self.root / "engine" / "prompts" / "system_hermes_football_only.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            bak = self._backup(p)
            p.write_text(
                "# HERMES OPERATOR\nPapel: diagnostico e correcoes AURA.\n"
                "paper_trade=true\nexecution_allowed=false\n"
                "PROIBIDO: apostas reais.\n",
                encoding="utf-8",
            )
            return CorrectionResult(True, fix_name, str(bak) if bak else None, "domain lock operador")
        if fix_name == "fix_desktop_json":
            cfg = self.root / "desktop" / "config" / "desktop.json"
            if not cfg.exists():
                return CorrectionResult(False, fix_name, message="desktop.json ausente")
            bak = self._backup(cfg)
            data = json.loads(cfg.read_text(encoding="utf-8"))
            app = data.setdefault("app", {})
            app["homepage"] = "http://127.0.0.1:8766/index.html"
            app["paperTradeOnly"] = True
            data.setdefault("security", {})["allowRealOrders"] = False
            cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return CorrectionResult(True, fix_name, str(bak) if bak else None, "homepage 8766")
        if fix_name == "set_execution_false":
            os.environ["EXECUTION_ALLOWED"] = "false"
            os.environ["PAPER_TRADE"] = "true"
            return CorrectionResult(True, fix_name, message="env forçado paper")
        if fix_name == "rotate_logs":
            logdir = self.root / "logs_supervisor"
            n = 0
            if logdir.exists():
                for f in logdir.glob("*.txt"):
                    if f.stat().st_size > 5_000_000:
                        self._backup(f)
                        f.write_text(f.read_text(encoding="utf-8", errors="replace")[-500000:], encoding="utf-8")
                        n += 1
            return CorrectionResult(True, fix_name, message=f"rotacionados={n}")
        return CorrectionResult(False, fix_name, message="fix não implementado")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("AURA_ROOT", "C:/aura"))
    ap.add_argument("--fix", required=True)
    args = ap.parse_args()
    r = CorrectionAgent(args.root).apply(args.fix)
    print(json.dumps(r.__dict__, ensure_ascii=False, indent=2))
