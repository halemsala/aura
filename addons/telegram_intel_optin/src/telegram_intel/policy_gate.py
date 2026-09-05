"""Operator pre-authorization gate for bulk Telegram publish (policy, not per-message click)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> float:
    return time.time()


@dataclass
class PublishCounters:
    hour_key: str = ""
    day_key: str = ""
    hour_count: int = 0
    day_count: int = 0
    last_ts: float = 0.0


@dataclass
class PolicyGate:
    policy_path: Path
    state_path: Path
    policy: dict[str, Any] = field(default_factory=dict)
    counters: PublishCounters = field(default_factory=PublishCounters)
    session_until: float = 0.0

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        if self.policy_path.exists():
            self.policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        else:
            self.policy = {"enabled": False, "auto_publish": {"enabled": False}}
        if self.state_path.exists():
            try:
                st = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.session_until = float(st.get("session_until", 0))
                c = st.get("counters") or {}
                self.counters = PublishCounters(
                    hour_key=c.get("hour_key", ""),
                    day_key=c.get("day_key", ""),
                    hour_count=int(c.get("hour_count", 0)),
                    day_count=int(c.get("day_count", 0)),
                    last_ts=float(c.get("last_ts", 0)),
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    def save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_until": self.session_until,
            "counters": {
                "hour_key": self.counters.hour_key,
                "day_key": self.counters.day_key,
                "hour_count": self.counters.hour_count,
                "day_count": self.counters.day_count,
                "last_ts": self.counters.last_ts,
            },
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def kill_switch_on(self) -> bool:
        env_name = (self.policy.get("kill_switch_env") or "AURA_TELEGRAM_KILL_SWITCH")
        return os.environ.get(env_name, "0").strip() in ("1", "true", "yes", "on")

    def grant_session(self, operator_token: str, expected_token: str, hours: float | None = None) -> dict[str, Any]:
        """One operator action: open an auto-publish window (e.g. 12h)."""
        auto = self.policy.get("auto_publish") or {}
        if auto.get("session_grant_requires_operator_token", True):
            if not expected_token or operator_token != expected_token:
                return {"ok": False, "reason": "invalid_operator_token"}
        h = hours if hours is not None else float(auto.get("session_grant_hours", 12))
        self.session_until = _now() + h * 3600
        self.save_state()
        return {"ok": True, "session_until": datetime.utcfromtimestamp(self.session_until).isoformat() + "Z", "hours": h}

    def revoke_session(self) -> dict[str, Any]:
        self.session_until = 0.0
        self.save_state()
        return {"ok": True, "reason": "session_revoked"}

    def _roll_counters(self) -> None:
        hour_key = datetime.utcnow().strftime("%Y%m%d%H")
        day_key = datetime.utcnow().strftime("%Y%m%d")
        if self.counters.hour_key != hour_key:
            self.counters.hour_key = hour_key
            self.counters.hour_count = 0
        if self.counters.day_key != day_key:
            self.counters.day_key = day_key
            self.counters.day_count = 0

    def content_ok(self, text: str) -> tuple[bool, str]:
        t = (text or "").lower()
        if self.policy.get("require_paper_advisory_language", True):
            req = [p.lower() for p in (self.policy.get("require_phrases_any") or [])]
            if req and not any(p in t for p in req):
                return False, "missing_paper_advisory_phrase"
        for bad in self.policy.get("forbid_phrases") or []:
            if bad.lower() in t:
                return False, f"forbid_phrase:{bad}"
        return True, "ok"

    def evaluate(
        self,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Returns decision: auto_send | queue | block."""
        meta = meta or {}
        if self.kill_switch_on():
            return {"decision": "block", "reason": "kill_switch"}
        if not self.policy.get("enabled"):
            return {"decision": "queue", "reason": "policy_disabled_use_queue"}

        ok_c, why = self.content_ok(text)
        if not ok_c:
            return {"decision": "block", "reason": why}

        auto = self.policy.get("auto_publish") or {}
        if not auto.get("enabled"):
            return {"decision": "queue", "reason": "auto_publish_off"}

        # session grant
        if auto.get("session_grant_requires_operator_token", True) and _now() > self.session_until:
            return {"decision": "queue", "reason": "no_active_session_grant"}

        # quiet hours
        qh = auto.get("quiet_hours_local") or {}
        if qh:
            hour = datetime.now().hour
            start, end = int(qh.get("start", 1)), int(qh.get("end", 7))
            if start <= end and start <= hour < end:
                return {"decision": "queue", "reason": "quiet_hours"}
            if start > end and (hour >= start or hour < end):
                return {"decision": "queue", "reason": "quiet_hours"}

        # red team / score
        rt = str(meta.get("red_team", meta.get("verdict", ""))).upper()
        need_rt = str(auto.get("only_if_red_team") or "").upper()
        if need_rt and need_rt not in ("", "ANY", "NONE"):
            if rt != need_rt:
                return {"decision": "queue", "reason": f"red_team_not_{need_rt}"}

        min_score = float(auto.get("min_score") or 0)
        score = meta.get("score")
        if min_score and score is not None and float(score) < min_score:
            return {"decision": "queue", "reason": "score_below_min"}

        markets = [m.lower() for m in (auto.get("markets_allowlist") or [])]
        mkt = str(meta.get("market", "")).lower()
        if markets and mkt and not any(x in mkt for x in markets):
            return {"decision": "block", "reason": "market_not_allowlisted"}

        self._roll_counters()
        max_h = int(auto.get("max_per_hour") or 12)
        max_d = int(auto.get("max_per_day") or 80)
        gap = float(auto.get("min_seconds_between") or 45)
        if self.counters.hour_count >= max_h:
            return {"decision": "queue", "reason": "max_per_hour"}
        if self.counters.day_count >= max_d:
            return {"decision": "queue", "reason": "max_per_day"}
        if self.counters.last_ts and (_now() - self.counters.last_ts) < gap:
            return {"decision": "queue", "reason": "min_interval"}

        return {"decision": "auto_send", "reason": "policy_ok"}

    def record_send(self) -> None:
        self._roll_counters()
        self.counters.hour_count += 1
        self.counters.day_count += 1
        self.counters.last_ts = _now()
        self.save_state()
