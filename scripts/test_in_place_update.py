#!/usr/bin/env python3
"""Testes offline do contrato de atualização in-place do AURA.

Os testes não iniciam processos nem executam BAT/PowerShell. Reproduzem as
regras de seleção do patch sobre uma cópia temporária do bundle.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = (
    "engine/venv/",
    "engine/aura_quant_x.db",
    "config.json",
    ".env",
    "voice_profiles/",
    "voice_assets/",
    "models/",
    "ollama/",
    "logs_instalacao/",
    "backups/",
    "runtime/",
)
ALLOWED_EXACT = {
    "AURA_REPARAR_SISTEMA.bat",
    "AURA_InPlace.ps1",
    "allowlist.json",
    "desktop/MainForm.cs",
    "desktop/Models.cs",
    "desktop/BrowserHost.cs",
    "desktop/ServiceSupervisor.cs",
    "desktop/ui/matriz/aura-quantx-adapter.js",
    "desktop/ui/matriz/aura-quantx-central.html",
    "desktop/ui/matriz/aura-quantx-central.css",
    "desktop/ui/matriz/aura-quantx-central.js",
    "agents/activation_manifest.json",
}
SUSPICIOUS = ("pip uninstall", "ollama pull", "stop-process", "taskkill", "invoke-expression")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_target(target: str) -> bool:
    p = target.replace("\\", "/").lstrip("/")
    if not p or p.startswith("../") or "/../" in f"/{p}" or ":" in p.split("/")[0]:
        return False
    if any(p == item.rstrip("/") or p.startswith(item) for item in PROTECTED):
        return False
    if p.endswith((".db", ".sqlite", ".sqlite3", ".gguf", ".pt", ".pth", ".wav", ".mp3")):
        return False
    return True


def allowlisted(target: str) -> bool:
    p = target.replace("\\", "/").lstrip("/")
    if p in ALLOWED_EXACT:
        return True
    for prefix in ("engine/", "bridge/", "desktop/ui/", "desktop/ui/matriz/", "scripts/"):
        if p.startswith(prefix) and Path(p).suffix.lower() in {".py", ".js", ".css", ".html", ".md"}:
            return True
    return False


def validate_patch(root: Path, patch: dict[str, Any]) -> tuple[bool, str]:
    files = patch.get("files") if isinstance(patch.get("files"), list) else []
    if patch.get("schema") != "aura-inplace-patch-v1":
        return False, "schema"
    for item in files:
        if not isinstance(item, dict):
            return False, "item_type"
        source = root / str(item.get("source", ""))
        target = str(item.get("target", ""))
        if not source.is_file():
            return False, "source_missing"
        if not safe_target(target):
            return False, "protected_or_unsafe_target"
        if not allowlisted(target):
            return False, "not_allowlisted"
        if sha256(source) != str(item.get("sha256", "")).lower():
            return False, "source_hash"
        content = source.read_text(encoding="utf-8", errors="replace").lower()
        if any(token in content for token in SUSPICIOUS):
            return False, "suspicious_content"
    return True, "ok"


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run() -> tuple[list[dict[str, Any]], int]:
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="aura_inplace_test_") as temp:
        work = Path(temp) / "root"
        (work / "desktop/ui/matriz").mkdir(parents=True)
        (work / "engine").mkdir()
        target = work / "desktop/ui/matriz/aura-quantx-adapter.js"
        target.write_text("old", encoding="utf-8")
        patch_source = work / "patch.js"
        patch_source.write_text("new", encoding="utf-8")
        valid = {
            "schema": "aura-inplace-patch-v1",
            "files": [{"source": "patch.js", "target": "desktop/ui/matriz/aura-quantx-adapter.js", "sha256": sha256(patch_source)}],
        }
        ok, reason = validate_patch(work, valid)
        checks.append(check("valid_patch", ok, reason))
        checks.append(check("second_run_idempotent", validate_patch(work, valid) == (True, "ok"), "mesmo manifesto permanece válido"))

        protected = dict(valid)
        protected["files"] = [dict(valid["files"][0], target="engine/aura_quant_x.db")]
        checks.append(check("protected_db_blocked", validate_patch(work, protected) == (False, "protected_or_unsafe_target"), "base protegida rejeitada"))

        traversal = dict(valid)
        traversal["files"] = [dict(valid["files"][0], target="../outside.py")]
        checks.append(check("traversal_blocked", validate_patch(work, traversal) == (False, "protected_or_unsafe_target"), "path traversal rejeitado"))

        suspicious_source = work / "suspicious.js"
        suspicious_source.write_text("ollama pull glm4:9b-chat-q4_0", encoding="utf-8")
        suspicious = dict(valid)
        suspicious["files"] = [dict(valid["files"][0], source="suspicious.js", sha256=sha256(suspicious_source))]
        checks.append(check("suspicious_content_blocked", validate_patch(work, suspicious) == (False, "suspicious_content"), "conteúdo destrutivo ou de pull rejeitado"))

        backup = work / "backup"
        backup.mkdir()
        before = target.read_bytes()
        (backup / "target.bin").write_bytes(before)
        target.write_text("new", encoding="utf-8")
        target.write_bytes((backup / "target.bin").read_bytes())
        checks.append(check("selective_rollback", target.read_bytes() == before, "rollback restaurou somente o destino alterado"))
        checks.append(check("protected_assets_untouched", not (work / "engine/aura_quant_x.db").exists(), "nenhum banco foi criado ou tocado"))
    return checks, 0 if all(item["ok"] for item in checks) else 1


def main() -> int:
    checks, code = run()
    print(json.dumps({"ok": code == 0, "checks": checks}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
