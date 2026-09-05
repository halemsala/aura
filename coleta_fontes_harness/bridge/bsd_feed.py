#!/usr/bin/env python3
"""
bsd_feed.py — Conector BSD (sports.bzzoiro.com) como fonte COMPLEMENTAR.

Regras inegociáveis:
- Nunca substitui SokkerPro (/api/ui/state + DOM).
- Apenas enriquece corners, incidents, xG, dangerous attacks.
- Todas as decisões finais continuam a passar pelo InvariantGate.
- Quota free respeitada (rate-limit local).

Config: config/bsd_api.json  ou  env BSD_API_KEY
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "bsd_api.json"
LOG_DIVERGENCE = ROOT / "data" / "bsd_vs_sokkerpro.jsonl"


@dataclass
class BSDConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://sports.bzzoiro.com/api/v2"
    timeout_sec: float = 8.0
    max_requests_per_minute: int = 20
    primary_source: str = "sokkerpro"
    role: str = "complementary"

    @classmethod
    def load(cls) -> "BSDConfig":
        cfg = cls()
        # 1. Ficheiro
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                cfg.enabled = bool(data.get("enabled", True))
                cfg.api_key = str(data.get("api_key", "") or "")
                cfg.base_url = str(data.get("base_url", cfg.base_url)).rstrip("/")
                cfg.timeout_sec = float(data.get("timeout_sec", 8))
                cfg.max_requests_per_minute = int(data.get("max_requests_per_minute", 20))
            except Exception as e:
                logger.warning("bsd_api.json inválido: %s", e)
        # 2. Env tem prioridade (permite rotação sem editar ficheiro)
        env_key = os.environ.get("BSD_API_KEY", "").strip()
        if env_key:
            cfg.api_key = env_key
        return cfg


class RateLimiter:
    def __init__(self, max_per_minute: int = 20):
        self.max = max_per_minute
        self.timestamps: List[float] = []

    def allow(self) -> bool:
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < 60]
        if len(self.timestamps) >= self.max:
            return False
        self.timestamps.append(now)
        return True


@dataclass
class BSDSnapshot:
    event_id: Optional[int] = None
    home: str = ""
    away: str = ""
    minute: Optional[int] = None
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    corners_home: Optional[int] = None
    corners_away: Optional[int] = None
    possession_home: Optional[float] = None
    possession_away: Optional[float] = None
    shots_home: Optional[int] = None
    shots_away: Optional[int] = None
    dangerous_attacks_home: Optional[int] = None
    dangerous_attacks_away: Optional[int] = None
    xg_home: Optional[float] = None
    xg_away: Optional[float] = None
    incidents: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "bsd"


class BSDFeed:
    """
    Cliente REST da BSD API — papel complementar.
    """

    def __init__(self, config: Optional[BSDConfig] = None):
        self.config = config or BSDConfig.load()
        self.limiter = RateLimiter(self.config.max_requests_per_minute)
        self._session_headers = {
            "Authorization": f"Token {self.config.api_key}",
            "User-Agent": "AURA-QuantX-BSD/1.0",
            "Accept": "application/json",
        }

    @property
    def enabled(self) -> bool:
        return self.config.enabled and bool(self.config.api_key)

    def _get(self, path: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        if not self.limiter.allow():
            logger.warning("BSD rate-limit local atingido")
            return None
        url = f"{self.config.base_url}/{path.lstrip('/')}"
        req = urllib.request.Request(url, headers=self._session_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            logger.warning("BSD HTTP %s: %s", e.code, e.reason)
            return None
        except Exception as e:
            logger.warning("BSD request failed: %s", e)
            return None

    def get_live_events(self) -> List[Dict[str, Any]]:
        data = self._get("events/live/")
        if not data:
            return []
        return data.get("results") or data.get("events") or []

    def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        return self._get(f"events/{event_id}/")

    def get_stats(self, event_id: int) -> Optional[Dict[str, Any]]:
        return self._get(f"events/{event_id}/stats/")

    def get_incidents(self, event_id: int) -> Optional[Dict[str, Any]]:
        return self._get(f"events/{event_id}/incidents/")

    def find_event_by_teams(self, home: str, away: str) -> Optional[int]:
        """Procura event_id em live pelo nome aproximado dos times."""
        events = self.get_live_events()
        home_l = home.lower().strip()
        away_l = away.lower().strip()
        for ev in events:
            h = str(ev.get("home_team") or ev.get("home") or "").lower()
            a = str(ev.get("away_team") or ev.get("away") or "").lower()
            if (home_l in h or h in home_l) and (away_l in a or a in away_l):
                return ev.get("id") or ev.get("event_id")
        return None

    def fetch_complementary(
        self,
        home: str,
        away: str,
        event_id: Optional[int] = None,
    ) -> Optional[BSDSnapshot]:
        """
        Obtém snapshot complementar para um jogo.
        Se event_id não for dado, tenta descobrir pelo nome dos times.
        """
        if not self.enabled:
            return None
        eid = event_id
        if eid is None:
            eid = self.find_event_by_teams(home, away)
        if eid is None:
            logger.debug("BSD: evento não encontrado para %s x %s", home, away)
            return None

        stats = self.get_stats(eid) or {}
        incidents_raw = self.get_incidents(eid) or {}
        event = self.get_event(eid) or {}

        # Normalização defensiva (estrutura da BSD pode variar)
        def _side(d: Dict, key: str, side: str) -> Any:
            if not d:
                return None
            if key in d:
                val = d[key]
                if isinstance(val, dict):
                    return val.get(side) or val.get(side[0])  # home/away or h/a
                return val
            # formatos alternativos
            side_key = f"{key}_{side}" if side in ("home", "away") else key
            return d.get(side_key)

        snap = BSDSnapshot(
            event_id=eid,
            home=str(event.get("home_team") or home),
            away=str(event.get("away_team") or away),
            minute=event.get("current_minute") or event.get("minute"),
            score_home=event.get("home_score"),
            score_away=event.get("away_score"),
            corners_home=_side(stats, "corners", "home"),
            corners_away=_side(stats, "corners", "away"),
            possession_home=_side(stats, "possession", "home"),
            possession_away=_side(stats, "possession", "away"),
            shots_home=_side(stats, "shots", "home") or _side(stats, "total_shots", "home"),
            shots_away=_side(stats, "shots", "away") or _side(stats, "total_shots", "away"),
            dangerous_attacks_home=_side(stats, "dangerous_attacks", "home"),
            dangerous_attacks_away=_side(stats, "dangerous_attacks", "away"),
            xg_home=_side(stats, "xg", "home") or _side(stats, "expected_goals", "home"),
            xg_away=_side(stats, "xg", "away") or _side(stats, "expected_goals", "away"),
            incidents=incidents_raw.get("results") or incidents_raw.get("incidents") or [],
            raw={"event": event, "stats": stats, "incidents": incidents_raw},
        )
        return snap

    def log_divergence(
        self,
        sokker: Dict[str, Any],
        bsd: BSDSnapshot,
    ) -> None:
        """Regista divergências SokkerPro vs BSD (forense)."""
        LOG_DIVERGENCE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "home": bsd.home,
            "away": bsd.away,
            "bsd_event_id": bsd.event_id,
            "sokker_corners_h": sokker.get("corners_home"),
            "sokker_corners_a": sokker.get("corners_away"),
            "bsd_corners_h": bsd.corners_home,
            "bsd_corners_a": bsd.corners_away,
            "sokker_minute": sokker.get("minute"),
            "bsd_minute": bsd.minute,
            "sokker_score": f"{sokker.get('score_home')}-{sokker.get('score_away')}",
            "bsd_score": f"{bsd.score_home}-{bsd.score_away}",
        }
        try:
            with open(LOG_DIVERGENCE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Falha ao escrever divergência BSD: %s", e)


# ---------------------------------------------------------------------------
# Helper de integração (chamado pelo FeedbackConnector / encode_game_events)
# ---------------------------------------------------------------------------

def enrich_with_bsd(
    sokker_view: Dict[str, Any],
    history: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Enriquece o match view do SokkerPro com dados BSD (se disponíveis).
    Retorna um dict novo; nunca muta o original.
    """
    out = dict(sokker_view)
    out["_sources"] = list(out.get("_sources") or ["sokkerpro"])
    if "sokkerpro" not in out["_sources"]:
        out["_sources"].append("sokkerpro")

    feed = BSDFeed()
    if not feed.enabled:
        out["_bsd"] = {"status": "disabled"}
        return out

    home = str(sokker_view.get("home") or sokker_view.get("home_team") or "")
    away = str(sokker_view.get("away") or sokker_view.get("away_team") or "")
    snap = feed.fetch_complementary(home, away)

    if snap is None:
        out["_bsd"] = {"status": "not_found"}
        return out

    # Merge conservador: BSD só preenche campos em falta ou confirma
    if out.get("corners_home") is None and snap.corners_home is not None:
        out["corners_home"] = snap.corners_home
    if out.get("corners_away") is None and snap.corners_away is not None:
        out["corners_away"] = snap.corners_away
    if out.get("xg_home") is None and snap.xg_home is not None:
        out["xg_home"] = snap.xg_home
    if out.get("xg_away") is None and snap.xg_away is not None:
        out["xg_away"] = snap.xg_away

    out["_bsd"] = {
        "status": "ok",
        "event_id": snap.event_id,
        "corners_home": snap.corners_home,
        "corners_away": snap.corners_away,
        "xg_home": snap.xg_home,
        "xg_away": snap.xg_away,
        "dangerous_attacks_home": snap.dangerous_attacks_home,
        "dangerous_attacks_away": snap.dangerous_attacks_away,
        "minute": snap.minute,
        "fetched_at": snap.fetched_at,
    }
    out["_sources"].append("bsd")

    # Log forense se houver divergência de corners
    try:
        feed.log_divergence(sokker_view, snap)
    except Exception:
        pass

    return out


if __name__ == "__main__":
    # Smoke test rápido
    logging.basicConfig(level=logging.INFO)
    cfg = BSDConfig.load()
    print(f"enabled={cfg.enabled} key_set={bool(cfg.api_key)} base={cfg.base_url}")
    feed = BSDFeed(cfg)
    live = feed.get_live_events()
    print(f"live events: {len(live)}")
    if live:
        first = live[0]
        print(f"first: {first.get('home_team')} x {first.get('away_team')} id={first.get('id')}")
