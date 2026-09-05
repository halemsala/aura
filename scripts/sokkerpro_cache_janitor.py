# -*- coding: utf-8 -*-
"""Purge SokkerPRO / WebView / interface cache older than 24 hours."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

TTL_SEC = 24 * 3600
NOW = time.time()

def _age(p: Path) -> float:
    try:
        return NOW - p.stat().st_mtime
    except OSError:
        return 0.0

def purge_dir(folder: Path, ttl: int = TTL_SEC) -> dict:
    removed, kept, bytes_freed = 0, 0, 0
    if not folder.exists():
        return {"path": str(folder), "removed": 0, "kept": 0, "bytes_freed": 0}
    for p in folder.rglob("*"):
        if not p.is_file():
            continue
        if p.name in {".gitkeep", "cache-index.json"}:
            kept += 1
            continue
        if _age(p) > ttl:
            try:
                bytes_freed += p.stat().st_size
                p.unlink()
                removed += 1
            except OSError:
                kept += 1
        else:
            kept += 1
    # drop empty dirs
    for d in sorted((x for x in folder.rglob("*") if x.is_dir()), reverse=True):
        try:
            next(d.iterdir())
        except StopIteration:
            try:
                d.rmdir()
            except OSError:
                pass
        except OSError:
            pass
    return {"path": str(folder), "removed": removed, "kept": kept, "bytes_freed": bytes_freed}

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    targets = [
        root / "cache" / "sokkerpro",
        root / "interface" / ".cache",
        local / "AURA_QUANT_X" / "sokkerpro_cache",
    ]
    wv = local / "AURA_QUANT_X"
    report = {"ttl_hours": 24, "targets": []}
    if wv.exists():
        for name in ("Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache"):
            for hit in wv.rglob(name):
                if hit.is_dir():
                    targets.append(hit)
    for t in targets:
        report["targets"].append(purge_dir(t))
    marker = root / "cache" / "last_janitor.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("JANITOR_OK ttl=24h removed=%s freed=%s" % (
        sum(x["removed"] for x in report["targets"]),
        sum(x["bytes_freed"] for x in report["targets"]),
    ))
    return 0

if __name__ == "__main__":
    sys.exit(main())
