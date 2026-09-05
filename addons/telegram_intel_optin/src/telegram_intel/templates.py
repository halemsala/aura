"""Message templates — paper/advisory, no profit promises."""
from __future__ import annotations
from typing import Any


DISCLAIMER = (
    "Analise paper/advisory AURA — nao e aconselhamento financeiro nem ordem real. "
    "execution_allowed=false."
)


def tip_corners_paper(meta: dict[str, Any]) -> str:
    home = meta.get("home", "?")
    away = meta.get("away", "?")
    market = meta.get("market", "escanteios")
    odd = meta.get("odd", "—")
    score = meta.get("score", "—")
    minute = meta.get("minute", "—")
    verdict = meta.get("red_team", meta.get("verdict", "—"))
    reasons = meta.get("reasons") or []
    reason_txt = "; ".join(reasons[:2]) if reasons else "—"
    return (
        f"<b>AURA Paper · {market}</b>\n"
        f"{home} vs {away}\n"
        f"Min {minute} · Placar {score} · Ref. odd {odd}\n"
        f"RedTeam: {verdict}\n"
        f"Nota: {reason_txt}\n"
        f"<i>{DISCLAIMER}</i>"
    )


def tip_generic_paper(text: str, meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    body = (text or "").strip()[:800]
    return f"<b>AURA Paper / advisory</b>\n{body}\n<i>{DISCLAIMER}</i>"
