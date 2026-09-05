"""Elite Squad Advisory — paper-only.

Modules: DataJanitor, RedTeamAdversary, OnlineThresholdTuner,
PostMatchForensics, ROIAuditorPaper.

NO Telegram, NO tip scrape, NO production YAML write, NO execution_allowed=true.
"""
from __future__ import annotations

from .elite_squad_advisory_stubs import (
    DATA_JANITOR,
    DEFAULT_LIMITS,
    FORENSICS,
    ONLINE_TUNER,
    RED_TEAM,
    ROI_AUDITOR,
    DataJanitor,
    OnlineThresholdTuner,
    PostMatchForensics,
    ROIAuditorPaper,
    RedTeamAdversary,
)

__all__ = [
    "DataJanitor",
    "RedTeamAdversary",
    "OnlineThresholdTuner",
    "PostMatchForensics",
    "ROIAuditorPaper",
    "DATA_JANITOR",
    "RED_TEAM",
    "ONLINE_TUNER",
    "FORENSICS",
    "ROI_AUDITOR",
    "DEFAULT_LIMITS",
]

PAPER_ONLY = True
EXECUTION_ALLOWED = False
