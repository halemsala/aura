"""Features temporais locais para análise de escanteios.

Este módulo recebe snapshots já coletados por uma fonte autorizada. Ele não
faz HTTP, não persiste payload bruto e não inicia polling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .contracts import CornerFeatures


_MAX_STALENESS_SECONDS = 180.0
_WINDOW_EDGE_TOLERANCE_SECONDS = 2.0


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(point: Mapping[str, Any], key: str) -> int:
    value = point.get(key, 0)
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def build_temporal_features(
    points: Iterable[Mapping[str, Any]],
    *,
    fixture_id: str | None = None,
    now: datetime | None = None,
) -> CornerFeatures:
    """Constrói um contrato imutável a partir de snapshots ordenáveis."""

    materialized = [point for point in points if isinstance(point, Mapping)]
    if not materialized:
        raise ValueError("at least one snapshot is required")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    parsed = [(point, _timestamp(point.get("timestamp"))) for point in materialized]
    parsed = [(point, stamp) for point, stamp in parsed if stamp is not None]
    if not parsed:
        raise ValueError("at least one valid timestamp is required")
    parsed.sort(key=lambda item: item[1])

    latest_point, latest_stamp = parsed[-1]
    # Tolerância curta para o skew entre timestamps de snapshots e o relógio
    # local; não altera o gate de frescor de 180 segundos.
    window_start = latest_stamp.timestamp() - 600.0 - _WINDOW_EDGE_TOLERANCE_SECONDS
    window = [(point, stamp) for point, stamp in parsed if stamp.timestamp() >= window_start]
    first_point, first_stamp = window[0]

    latest_corners = _number(latest_point, "corners_home") + _number(latest_point, "corners_away")
    first_corners = _number(first_point, "corners_home") + _number(first_point, "corners_away")
    corner_delta = max(0, latest_corners - first_corners)
    attack_delta = (
        _number(latest_point, "attacks_home")
        + _number(latest_point, "attacks_away")
        - _number(first_point, "attacks_home")
        - _number(first_point, "attacks_away")
    )
    dangerous_delta = (
        _number(latest_point, "dangerous_home")
        + _number(latest_point, "dangerous_away")
        - _number(first_point, "dangerous_home")
        - _number(first_point, "dangerous_away")
    )
    span_minutes = max(1.0, (latest_stamp - first_stamp).total_seconds() / 60.0)
    freshness = max(0.0, (current - latest_stamp).total_seconds())
    source_count = len({str(point.get("source") or "unknown") for point, _ in window})
    quality = 1.0
    if freshness > _MAX_STALENESS_SECONDS:
        quality = 0.0
    elif len(window) < 2:
        quality = 0.5
    elif source_count == 0:
        quality = 0.0

    resolved_fixture = fixture_id or str(latest_point.get("fixture_id") or "unknown")
    minute = _number(latest_point, "minute")
    return CornerFeatures(
        fixture_id=resolved_fixture,
        minute=min(130, minute),
        corner_total=latest_corners,
        corner_delta_10m=corner_delta,
        attack_delta_10m=attack_delta,
        dangerous_delta_10m=dangerous_delta,
        corner_rate_10m=round(corner_delta / span_minutes * 10.0, 4),
        evidence_count=len(window),
        freshness_seconds=round(freshness, 3),
        quality_score=quality,
        source_count=source_count,
    )


__all__ = ["build_temporal_features"]
