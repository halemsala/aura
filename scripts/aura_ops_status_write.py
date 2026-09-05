#!/usr/bin/env python3
"""Write ops_status.json for Tools Hub (paper-only, local files only)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(os.environ.get("AURA_ROOT", r"C:\aura"))
if not (ROOT / "engine").exists():
    ROOT = Path(__file__).resolve().parents[1]

OUT = ROOT / "desktop" / "ui" / "matriz_v22" / "ops_status.json"
QUEUE = ROOT / "data" / "telegram_intel" / "tip_queue.json"
POLICY_STATE = ROOT / "data" / "telegram_intel" / "policy_state.json"
KILL = ROOT / "data" / "telegram_intel" / "kill_switch.on"
LAST_VETO = ROOT / "data" / "elite_squad" / "last_veto.json"
SUGGEST = ROOT / "engine" / "data" / "threshold_suggestions.json"


def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return default


def vram_snapshot() -> dict:
    info = {"ok": False, "gpus": [], "hint": "nvidia-smi indisponivel"}
    try:
        import subprocess

        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return info
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                used, total = float(parts[2]), float(parts[3])
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "mem_used_mb": used,
                        "mem_total_mb": total,
                        "mem_pct": round(100.0 * used / total, 1) if total else 0,
                        "util_pct": float(parts[4]),
                    }
                )
        info = {"ok": True, "gpus": gpus, "hint": "ok"}
    except Exception as e:
        info["hint"] = str(e)
    return info


def main() -> None:
    queue = _load(QUEUE, {"items": []})
    items = queue.get("items") or []
    counts = {"pending": 0, "sent": 0, "blocked": 0, "dry_run": 0, "failed": 0}
    for it in items:
        st = str(it.get("status") or "pending")
        counts[st] = counts.get(st, 0) + 1
    recent = sorted(items, key=lambda x: x.get("created_at") or 0, reverse=True)[:8]

    kill = KILL.exists() or os.environ.get("AURA_TELEGRAM_KILL_SWITCH", "0") in ("1", "true", "yes")
    policy_state = _load(POLICY_STATE, {})
    last_veto = _load(LAST_VETO, {})
    suggestions = _load(SUGGEST, {})

    payload = {
        "generated_at": time.time(),
        "generated_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paper_trade": True,
        "execution_allowed": False,
        "telegram": {
            "kill_switch": kill,
            "queue_counts": counts,
            "queue_total": len(items),
            "recent": [
                {
                    "id": r.get("id"),
                    "status": r.get("status"),
                    "preview": str(r.get("text") or "")[:120],
                    "created_at": r.get("created_at"),
                }
                for r in recent
            ],
            "session_until": policy_state.get("session_until"),
            "counters": policy_state.get("counters"),
        },
        "elite_squad": {
            "last_veto": last_veto,
            "threshold_suggestions": {
                "applied": suggestions.get("applied", False),
                "suggestions": suggestions.get("suggestions"),
                "generated_at": suggestions.get("generated_at"),
            },
        },
        "vram": vram_snapshot(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(OUT))


if __name__ == "__main__":
    main()
