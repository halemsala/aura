#!/usr/bin/env python3
"""Verifica a ativação declarativa do primeiro arranque do AURA.

A verificação é read-only: não importa agentes, não inicia serviços e não executa
funções. Confirma que o catálogo canónico e a interface Matriz estão instalados.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_AGENTS = 38  # V25O (2026-08-24): manifest ampliado de 34->38 (browser_agent,
                      # cross_site_analyst, odds_quality_monitor, cache_integration
                      # + corner_independent_v7, mora_master_agent). Ver
                      # docs/historico/ATUALIZACAO_V25O_ATIVAR_TUDO.txt
EXPECTED_TOOLS = 13
REQUIRED_MATRIX = (
    "desktop/ui/matriz_v22/index.html",
    "desktop/ui/matriz_v22/manifest.webmanifest",
    "desktop/ui/matriz_v22/sw.js",
)
GUARDS = ("PAPER TRADE", "PLAN_ONLY", "execution_allowed")



def _sanitize_root(root: Path) -> Path:
    text = str(root).strip().strip('"').strip("'")
    # Windows: remove accidental embedded quotes from BAT %~dp0 quoting bugs
    text = text.replace('"', '')
    p = Path(text).expanduser()
    try:
        p = p.resolve()
    except OSError:
        p = Path(text)
    return p


def check(root: Path) -> tuple[list[dict[str, Any]], int]:
    root = _sanitize_root(root)
    results: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    marker = root / "PACKAGE_RELEASE.txt"
    add("package_marker", marker.is_file(), marker.read_text(encoding="utf-8", errors="replace").strip() if marker.is_file() else f"missing @ {marker}")

    manifest_path = root / "agents" / "activation_manifest.json"
    if not manifest_path.is_file():
        add("activation_manifest", False, f"agents/activation_manifest.json ausente @ {manifest_path}")
        return results, 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add("activation_manifest", False, f"inválido: {exc}")
        return results, 1

    agents = manifest.get("agents") if isinstance(manifest.get("agents"), dict) else {}
    tools = manifest.get("tools") if isinstance(manifest.get("tools"), dict) else {}
    add("agent_count", len(agents) == EXPECTED_AGENTS, f"{len(agents)} / {EXPECTED_AGENTS}")
    add("tool_count", len(tools) == EXPECTED_TOOLS, f"{len(tools)} / {EXPECTED_TOOLS}")

    missing: list[str] = []
    disabled: list[str] = []
    for agent_id, spec in agents.items():
        path_text = str(spec.get("path") or "") if isinstance(spec, dict) else ""
        if not path_text or not (root / path_text).is_file():
            missing.append(f"{agent_id}:{path_text}")
        if isinstance(spec, dict) and spec.get("status") != "enabled":
            disabled.append(agent_id)
    add("agent_sources", not missing, ", ".join(missing) if missing else "todas as fontes presentes")
    add("agent_enabled", not disabled, ", ".join(disabled) if disabled else "todos os agentes declarados enabled")

    for relative in REQUIRED_MATRIX:
        path = root / relative
        add(f"matrix:{relative}", path.is_file(), "presente" if path.is_file() else "ausente")
    matrix_asset_dir = root / "desktop" / "ui" / "matriz_v22" / "assets"
    matrix_js = list(matrix_asset_dir.glob("*.js")) if matrix_asset_dir.is_dir() else []
    matrix_css = list(matrix_asset_dir.glob("*.css")) if matrix_asset_dir.is_dir() else []
    add("matrix:compiled_assets", bool(matrix_js and matrix_css), f"js={len(matrix_js)}; css={len(matrix_css)}")
    knowledge_required = ("engine/knowledge_review_gate.py", "knowledge/inbox/knowledge_candidates.jsonl", "knowledge/approved/knowledge.jsonl", "knowledge/review_decisions.jsonl")
    for relative in knowledge_required:
        path = root / relative
        add(f"knowledge:{relative}", path.is_file(), "presente" if path.is_file() else "ausente")

    text_files = [root / "engine/server.py", root / "engine/agent_registry.py", root / "engine/knowledge_review_gate.py", root / REQUIRED_MATRIX[0]]
    joined = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in text_files if path.is_file())
    for guard in GUARDS:
        add(f"guard:{guard}", guard.lower() in joined.lower(), "marcador presente" if guard.lower() in joined.lower() else "marcador ausente")

    ok = all(item["ok"] for item in results)
    return results, 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    results, code = check(_sanitize_root(args.root))
    print(json.dumps({"ok": code == 0, "expected_agents": EXPECTED_AGENTS, "expected_tools": EXPECTED_TOOLS, "checks": results}, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
