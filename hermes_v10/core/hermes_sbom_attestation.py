#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI-BOM builder + optional cosign (graceful without cosign)."""
from __future__ import annotations
import hashlib, json, subprocess, time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class AIComponent:
    name: str
    version: str
    kind: str
    source: str
    hash_sha256: str
    license: str = "UNKNOWN"

class SBOMBuilder:
    def build_ai_bom(self, root: Path, models: Optional[List[dict]] = None) -> dict:
        components = []
        try:
            proc = subprocess.run(["pip", "list", "--format=json"], capture_output=True, text=True, timeout=30)
            for pkg in json.loads(proc.stdout or "[]"):
                components.append(asdict(AIComponent(pkg["name"], pkg["version"], "python-pkg", "pypi", "")))
        except Exception:
            pass
        for f in [
            "core/hermes_constitution_engine.py",
            "core/hermes_constitution_engine_quantum.py",
            "hermes_config_ultra.json",
        ]:
            p = root / f
            if p.exists():
                components.append(asdict(AIComponent(
                    f, "N/A", "binary", "local", hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                )))
        for m in models or []:
            components.append(asdict(AIComponent(
                m.get("name", "?"), m.get("version", "?"), "model",
                m.get("source", "?"), m.get("hash", "?"), m.get("license", "UNKNOWN")
            )))
        return {
            "schema": "AI-BOM-1.0",
            "generated_at": time.time(),
            "slsa_level": 2,
            "components": components,
            "provenance": {"builder": "hermes-sbom-builder", "attestation": "sha256-local"},
        }

    def sign_with_sigstore(self, artifact_path: Path) -> bool:
        try:
            proc = subprocess.run(
                ["cosign", "sign-blob", "--yes", str(artifact_path)],
                capture_output=True, text=True, timeout=60,
            )
            return proc.returncode == 0
        except FileNotFoundError:
            return False

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    bom = SBOMBuilder().build_ai_bom(root, models=[{"name": "llama3.2:3b", "version": "local", "source": "ollama"}])
    out = root / "data" / "ai_bom.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bom, indent=2), encoding="utf-8")
    print("components", len(bom["components"]), "->", out)
