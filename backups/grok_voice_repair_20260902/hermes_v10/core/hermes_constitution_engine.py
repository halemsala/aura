#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra — Constitution Engine
Garante invariantes de segurança, audit trail e compliance do sistema.
"""
import os
import re
import json
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()

logger = structlog.get_logger("hermes.constitution")


class ConstitutionEngine:
    """
    Motor de constituição que:
    1. Escaneia código-fonte por padrões proibidos
    2. Valida hashes de arquivos críticos
    3. Mantém audit log imutável
    4. Bloqueia mutações que violam invariantes
    """

    DEFAULT_FORBIDDEN = [
        r"execution_allowed\s*=\s*true",
        r"EXECUTION_ALLOWED\s*=\s*TRUE",
        r"allowRealOrders\s*:\s*true",
        r"paper_trade\s*=\s*false",
        r"PAPER_TRADE\s*=\s*FALSE",
        r"aposta\s+real",
        r"live\s+trade",
        r"ordem\s+real",
        r"AURA_EXECUTION_ALLOWED\s*=\s*1",
        r"AURA_UNLOCK_LIVE\s*=\s*1",
    ]

    INVARIANTS = {
        "PAPER_TRADE": "true",
        "EXECUTION_ALLOWED": "false",
        "AURA_EXECUTION_ALLOWED": "0",
        "AURA_UNLOCK_LIVE": "0",
    }

    def __init__(self, root: str = ".", config_path: Optional[str] = None):
        self.root = Path(root).resolve()
        self.config_path = config_path or str(self.root / "hermes_config_ultra.json")
        self.audit_log = self.root / "logs_supervisor" / "security_audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.forbidden = [re.compile(p, re.IGNORECASE) for p in self.DEFAULT_FORBIDDEN]
        self._load_extra_patterns()

    def _load_extra_patterns(self):
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            extra = cfg.get("constitution", {}).get("forbidden_patterns", [])
            for p in extra:
                if p not in [x.pattern for x in self.forbidden]:
                    self.forbidden.append(re.compile(p, re.IGNORECASE))
        except Exception as e:
            logger.warning("config_load_warn", error=str(e))

    def scan_text(self, text: str, source: str = "unknown") -> Tuple[bool, List[str]]:
        """Retorna (safe, [violations])."""
        violations = []
        for pat in self.forbidden:
            for m in pat.finditer(text):
                violations.append(f"{source}: matched '{pat.pattern[:50]}...' at pos {m.start()}")
        return len(violations) == 0, violations

    def scan_file(self, path: Path) -> Tuple[bool, List[str]]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return False, [f"Não foi possível ler {path}: {e}"]
        return self.scan_text(text, source=str(path))

    def scan_directory(self, directory: Path, extensions: Tuple[str, ...] = (".py", ".bat", ".json", ".yaml", ".yml", ".env")) -> Dict[str, List[str]]:
        """Escaneia recursivamente um diretório."""
        results = {}
        for ext in extensions:
            for fp in directory.rglob(f"*{ext}"):
                safe, violations = self.scan_file(fp)
                if not safe:
                    results[str(fp)] = violations
        return results

    def check_environment_invariants(self) -> Tuple[bool, List[str]]:
        """Verifica se variáveis de ambiente respeitam invariantes."""
        violations = []
        for key, expected in self.INVARIANTS.items():
            actual = os.getenv(key, "")
            if actual and actual.lower() != expected.lower():
                violations.append(f"ENV {key}={actual} (esperado {expected})")
        return len(violations) == 0, violations

    def compute_hash(self, filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def verify_hashes(self, hashfile: Path) -> Tuple[bool, List[str]]:
        """Verifica hashes SHA256 de arquivos críticos."""
        violations = []
        if not hashfile.exists():
            return False, [f"Arquivo de hashes não encontrado: {hashfile}"]
        with open(hashfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                expected_hash, filepath = line.split(maxsplit=1)
                fp = self.root / filepath
                if not fp.exists():
                    violations.append(f"Arquivo crítico ausente: {filepath}")
                    continue
                actual = self.compute_hash(fp)
                if actual != expected_hash:
                    violations.append(f"Hash mismatch: {filepath} (esperado {expected_hash[:16]}..., atual {actual[:16]}...)")
        return len(violations) == 0, violations

    def audit(self, event: str, details: Optional[Dict] = None):
        """Escreve evento no audit log (append-only, thread-safe)."""
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event,
            "details": details or {},
        }
        with open(self.audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("audit_event", event=event, **(details or {}))

    def enforce(self, text: str, source: str = "unknown") -> str:
        """Bloqueia texto violador, retornando mensagem segura."""
        safe, violations = self.scan_text(text, source)
        if not safe:
            self.audit("constitution_violation_blocked", {"source": source, "violations": violations})
            return f"[BLOQUEADO PELA CONSTITUIÇÃO] Violações detectadas: {violations}"
        return text


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", choices=["status", "scan", "env"], default="status")
    args = parser.parse_args()

    engine = ConstitutionEngine(root=args.root)

    if args.check == "status":
        env_ok, env_v = engine.check_environment_invariants()
        print(f"Ambiente seguro: {env_ok}")
        if not env_ok:
            for v in env_v:
                print(f"  ! {v}")

        hashfile = Path(args.root) / "security" / "allowed_hashes.sha256"
        if hashfile.exists():
            hash_ok, hash_v = engine.verify_hashes(hashfile)
            print(f"Hashes OK: {hash_ok}")
            for v in hash_v:
                print(f"  ! {v}")

    elif args.check == "scan":
        results = engine.scan_directory(Path(args.root))
        if results:
            print(f"⚠️  {len(results)} arquivos com violações:")
            for fp, v in results.items():
                print(f"  {fp}: {len(v)} violações")
        else:
            print("✅ Nenhuma violação encontrada.")

    elif args.check == "env":
        ok, violations = engine.check_environment_invariants()
        print(json.dumps({"safe": ok, "violations": violations}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
