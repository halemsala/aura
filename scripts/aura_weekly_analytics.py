#!/usr/bin/env python3
"""Job semanal: journals -> relatorio markdown. Rodar fora do horario de jogos."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.core.analytics import Analytics  # noqa: E402
from engine.core.replay import scan_replay_files  # noqa: E402


def main() -> int:
    data = ROOT / "engine" / "data"
    data.mkdir(parents=True, exist_ok=True)
    # DuckDB se disponivel; senao SQLite transparente
    db_path = data / "analytics.duckdb"
    an = Analytics(db_path, prefer_duckdb=True)

    feed_paths = scan_replay_files(ROOT / "bridge")
    if not feed_paths:
        feed_paths = scan_replay_files(ROOT / "bridge", recursive=True)
    dec_paths = scan_replay_files(data)
    conf_paths = list(data.glob("**/conformal*.jsonl*")) + list(data.glob("**/*conformal*.jsonl*"))

    print(f"[analytics] feed files: {len(feed_paths)}")
    print(f"[analytics] decision files: {len(dec_paths)}")
    st = an.load_feed(feed_paths)
    print(f"[analytics] load_feed: {st}")
    nev = an.refresh_corner_events()
    print(f"[analytics] corner_events: {nev}")
    an.load_decisions(dec_paths)
    an.load_conformal(conf_paths or dec_paths)
    filled = an.fill_decision_outcomes(horizon=10)
    print(f"[analytics] outcomes filled: {filled}")

    report = an.full_report()
    out = data / "weekly_report.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\n[ok] relatorio salvo em {out}")
    an.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
