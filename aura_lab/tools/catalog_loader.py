#!/usr/bin/env python3
"""Carrega e valida o Failure Mode Catalog do AURA LAB (somente leitura)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "catalog" / "failure_modes_v1.yaml"
ID_RE = re.compile(r"^FM-[A-Z0-9]+-[0-9]{3}$")
REQUIRED = {
    "id",
    "title",
    "severity",
    "service",
    "symptom",
    "detect",
    "repair_steps",
    "verify",
    "lab_safe",
}


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML não instalado. pip install pyyaml")
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("catálogo deve ser um mapping YAML")
    return data


def validate_mode(mode: dict[str, Any], index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(mode, dict):
        return [f"[{index}] entrada não é objeto"]
    missing = REQUIRED - set(mode.keys())
    if missing:
        errors.append(f"[{index}] faltam campos: {sorted(missing)}")
    fid = mode.get("id")
    if fid is not None and not ID_RE.match(str(fid)):
        errors.append(f"[{index}] id inválido: {fid!r}")
    if not isinstance(mode.get("repair_steps"), list) or not mode.get("repair_steps"):
        errors.append(f"[{index}] repair_steps deve ser lista não vazia")
    if not isinstance(mode.get("verify"), list) or not mode.get("verify"):
        errors.append(f"[{index}] verify deve ser lista não vazia")
    if not isinstance(mode.get("lab_safe"), bool):
        errors.append(f"[{index}] lab_safe deve ser bool")
    detect = mode.get("detect")
    if not isinstance(detect, dict) or "method" not in detect:
        errors.append(f"[{index}] detect.method obrigatório")
    return errors


def validate_catalog(data: dict[str, Any]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    modes = data.get("failure_modes")
    if not isinstance(modes, list) or not modes:
        return [], ["failure_modes deve ser lista não vazia"]
    seen: set[str] = set()
    clean: list[dict] = []
    for i, mode in enumerate(modes):
        errors.extend(validate_mode(mode, i))
        if isinstance(mode, dict):
            fid = mode.get("id")
            if isinstance(fid, str):
                if fid in seen:
                    errors.append(f"id duplicado: {fid}")
                seen.add(fid)
            clean.append(mode)
    return clean, errors


def match_symptom(modes: list[dict], text: str, limit: int = 5) -> list[tuple[float, dict]]:
    """Score simples por tokens no título/sintoma/tags (sem LLM)."""
    needle = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not needle:
        return []
    tokens = [t for t in re.split(r"[^\w]+", needle) if len(t) > 2]
    scored: list[tuple[float, dict]] = []
    for mode in modes:
        blob = " ".join(
            [
                str(mode.get("title", "")),
                str(mode.get("symptom", "")),
                " ".join(mode.get("tags") or []),
                str(mode.get("service", "")),
            ]
        ).lower()
        score = 0.0
        for t in tokens:
            if t in blob:
                score += 1.0
                # boost tokens that appear in title (produtividade do match)
                if t in str(mode.get("title", "")).lower():
                    score += 0.5
        if mode.get("id") and mode["id"].lower().replace("-", "") in needle.replace("-", ""):
            score += 3.0
        if score > 0:
            scored.append((score, mode))
    scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    return scored[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA LAB catalog loader")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--match", type=str, default="", help="sintoma em texto livre")
    parser.add_argument("--json", action="store_true", help="saída JSON")
    args = parser.parse_args()

    if not args.catalog.is_file():
        print(f"ERRO: catálogo não encontrado: {args.catalog}", file=sys.stderr)
        return 2

    data = load_yaml(args.catalog)
    modes, errors = validate_catalog(data)
    if errors:
        print("VALIDAÇÃO FALHOU:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.match:
        hits = match_symptom(modes, args.match)
        if args.json:
            out = [
                {
                    "score": s,
                    "id": m.get("id"),
                    "title": m.get("title"),
                    "severity": m.get("severity"),
                    "service": m.get("service"),
                }
                for s, m in hits
            ]
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"Catálogo OK — {len(modes)} modos. Matches para: {args.match!r}\n")
            for score, m in hits:
                print(f"  [{score:.1f}] {m.get('id')}  {m.get('title')}  ({m.get('severity')})")
            if not hits:
                print("  (nenhum match — AGUARDA / enriquecer sintoma)")
        return 0

    if args.json:
        print(json.dumps({"version": data.get("version"), "count": len(modes), "ids": [m.get("id") for m in modes]}, ensure_ascii=False, indent=2))
    else:
        print(f"OK — {len(modes)} failure modes em {args.catalog}")
        for m in modes:
            flag = "LAB" if m.get("lab_safe") else "DOC"
            print(f"  {m.get('id'):16} [{flag}] {m.get('severity'):8} {m.get('title')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
