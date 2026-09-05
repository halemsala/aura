# engine/infra/code_signature.py
from __future__ import annotations
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

SECRET_ENV = "AURA_CODE_SIGN_SECRET"

def _secret() -> bytes:
    value = os.environ.get(SECRET_ENV, "").strip()
    if not value:
        raise RuntimeError(f"{SECRET_ENV} não configurado; assinatura desabilitada por segurança")
    return value.encode("utf-8")
MANIFEST_PATH = Path("code_signatures.json")

CRITICAL_PATHS = [
    "engine/engine_core.py",
    "engine/server.py",
    "engine/aura_director_agent.py",
    "app_aura_local.py",
    "bridge/glm5_inference_bridge.py",
    "bridge/jarvis_voice_server.py",
]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sign_digest(digest: str) -> str:
    return hmac.new(_secret(), digest.encode(), hashlib.sha256).hexdigest()


def build_manifest(root: Path = Path(".")) -> Dict[str, dict]:
    manifest: Dict[str, dict] = {}
    for rel in CRITICAL_PATHS:
        p = root / rel
        if not p.exists():
            manifest[rel] = {"exists": False}
            continue
        dig = file_sha256(p)
        manifest[rel] = {
            "exists": True,
            "sha256": dig,
            "signature": sign_digest(dig),
            "size": p.stat().st_size,
        }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_manifest(root: Path = Path("."), manifest_path: Path = MANIFEST_PATH) -> Dict[str, object]:
    if not os.environ.get(SECRET_ENV, "").strip():
        return {"ok": False, "error": "signing_secret_missing", "secret_env": SECRET_ENV, "results": {}}
    if not manifest_path.exists():
        return {"ok": False, "error": "manifest_missing", "results": {}}
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = {}
    all_ok = True
    for rel, meta in expected.items():
        p = root / rel
        if not meta.get("exists"):
            results[rel] = {"status": "skipped"}
            continue
        if not p.exists():
            results[rel] = {"status": "MISSING"}
            all_ok = False
            continue
        dig = file_sha256(p)
        sig_ok = hmac.compare_digest(sign_digest(dig), meta.get("signature", ""))
        hash_ok = dig == meta.get("sha256")
        status = "OK" if sig_ok and hash_ok else "TAMPERED"
        if status != "OK":
            all_ok = False
        results[rel] = {"status": status, "sha256": dig}
    return {"ok": all_ok, "results": results}


if __name__ == "__main__":
    m = build_manifest()
    print(json.dumps(verify_manifest(), indent=2))
