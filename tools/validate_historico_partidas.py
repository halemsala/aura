from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

REQUIRED = {
    "fixture_id", "utc_date", "league", "home_team", "away_team", "status",
    "home_score", "away_score", "source",
}
OPTIONAL_NUMERIC = {
    "home_corners", "away_corners", "home_yellow_cards", "away_yellow_cards",
    "home_red_cards", "away_red_cards",
}
ALL_COLUMNS = REQUIRED | OPTIONAL_NUMERIC


def nonnegative_int(value: str, field: str, row: int) -> int | None:
    if value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"linha {row}: {field} não é inteiro") from exc
    if parsed < 0:
        raise ValueError(f"linha {row}: {field} não pode ser negativo")
    return parsed


def validate(path: Path) -> dict:
    errors: list[str] = []
    accepted = 0
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED - columns)
        unknown = sorted(columns - ALL_COLUMNS)
        if missing:
            errors.append(f"colunas obrigatórias ausentes: {', '.join(missing)}")
        if unknown:
            errors.append(f"colunas desconhecidas: {', '.join(unknown)}")
        for row_number, row in enumerate(reader, start=2):
            try:
                fixture_id = (row.get("fixture_id") or "").strip()
                if not fixture_id:
                    raise ValueError(f"linha {row_number}: fixture_id vazio")
                if fixture_id in seen:
                    raise ValueError(f"linha {row_number}: fixture_id duplicado: {fixture_id}")
                seen.add(fixture_id)
                if (row.get("status") or "").strip().upper() != "FINISHED":
                    raise ValueError(f"linha {row_number}: status deve ser FINISHED")
                datetime.fromisoformat((row.get("utc_date") or "").strip().replace("Z", "+00:00"))
                for field in ("home_score", "away_score", *OPTIONAL_NUMERIC):
                    nonnegative_int((row.get(field) or "").strip(), field, row_number)
                for field in ("league", "home_team", "away_team", "source"):
                    if not (row.get(field) or "").strip():
                        raise ValueError(f"linha {row_number}: {field} vazio")
                accepted += 1
            except ValueError as exc:
                errors.append(str(exc))
    return {"ok": not errors, "accepted": accepted, "errors": errors, "input": str(path)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: python validate_historico_partidas.py arquivo.csv")
    result = validate(Path(sys.argv[1]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
