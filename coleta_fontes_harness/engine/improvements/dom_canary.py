# dom_canary.py
# DOM/API Capture Canary — detecta fontes silenciosamente inativas
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceStatus:
    name: str
    last_seen_mono: float
    last_value: Any = None
    ok_count: int = 0
    fail_count: int = 0
    status: str = "UNKNOWN"   # ACTIVE | INACTIVE | DEGRADED


class DomApiCaptureCanary:
    """
    Registra a última vez que cada fonte (WoM, H2H, xG, market, pressure…)
    produziu dado válido. Se silêncio > limiar → SOURCE_INACTIVE explícito.
    """

    def __init__(self, silence_warn_s: float = 25.0, silence_crit_s: float = 60.0):
        self.silence_warn_s = silence_warn_s
        self.silence_crit_s = silence_crit_s
        self._sources: Dict[str, SourceStatus] = {}

    def beat(self, source: str, value: Any = None) -> None:
        now = time.monotonic()
        st = self._sources.get(source)
        if st is None:
            st = SourceStatus(name=source, last_seen_mono=now, last_value=value, ok_count=1, status="ACTIVE")
            self._sources[source] = st
        else:
            st.last_seen_mono = now
            st.last_value = value
            st.ok_count += 1
            st.status = "ACTIVE"

    def fail(self, source: str) -> None:
        st = self._sources.get(source)
        if st is None:
            st = SourceStatus(name=source, last_seen_mono=0.0, fail_count=1, status="INACTIVE")
            self._sources[source] = st
        else:
            st.fail_count += 1

    def evaluate(self) -> Dict[str, Any]:
        now = time.monotonic()
        report = {}
        any_critical = False
        for name, st in self._sources.items():
            age = now - st.last_seen_mono if st.last_seen_mono > 0 else 9999.0
            if age >= self.silence_crit_s:
                st.status = "INACTIVE"
                any_critical = True
            elif age >= self.silence_warn_s:
                st.status = "DEGRADED"
            else:
                st.status = "ACTIVE"
            report[name] = {
                "status": st.status,
                "age_s": round(age, 1),
                "ok": st.ok_count,
                "fail": st.fail_count,
                "last_value_preview": str(st.last_value)[:80] if st.last_value is not None else None,
            }
        return {
            "sources": report,
            "any_critical": any_critical,
            "code": "SOURCE_INACTIVE" if any_critical else "SOURCES_OK",
            "timestamp": time.time(),
        }
