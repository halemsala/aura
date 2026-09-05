from __future__ import annotations
import threading
import time
import hashlib
import json
from typing import Any, Dict, Optional, Tuple


class LLMSemanticCache:
    INTENT_BUCKETS = ("status", "trading", "pre_alert", "advisory", "other")
    def __init__(self, ttl: float = 30.0, maxsize: int = 512):
        self.hits = 0
        self.misses = 0
        self._ttl = float(ttl)
        self._maxsize = int(maxsize)
        self._store: dict = {}
        self._lock = threading.Lock()

    def get(self, intent: str, state_hash: str) -> Optional[str]:
        key = (intent, state_hash)
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            if time.time() > item["expires"]:
                self._store.pop(key, None)
                return None
            return item["value"]

    def set(self, intent: str, state_hash: str, response: str) -> None:
        key = (intent, state_hash)
        with self._lock:
            self._store[key] = {"value": response, "expires": time.time() + self._ttl}
            while len(self._store) > self._maxsize:
                self._store.pop(next(iter(self._store)), None)

    def _feature_key(self, features: Dict[str, Any]) -> str:
        critical = {
            "fixture_id": features.get("fixture_id"),
            "minute": features.get("minute"),
            "score": features.get("score"),
            "corners_total": features.get("corners_total"),
            "wom_trend": features.get("wom_trend"),
            "route": features.get("route"),
            "query": features.get("query"),
        }
        raw = json.dumps(critical, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_features(self, features: Dict[str, Any]) -> Optional[str]:
        """Consulta por estado crítico da partida, sem mudar a API legada."""
        state_hash = self._feature_key(features)
        value = self.get(str(features.get("route") or "other"), state_hash)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def set_features(self, features: Dict[str, Any], response: str) -> None:
        state_hash = self._feature_key(features)
        self.set(str(features.get("route") or "other"), state_hash, response)

    def invalidate(self, intent: str) -> None:
        with self._lock:
            for k in [k for k in self._store if k[0] == intent]:
                self._store.pop(k, None)



    def audit(self) -> dict:
        total = getattr(self, "hits", 0) + getattr(self, "misses", 0)
        return {
            "hits": getattr(self, "hits", 0),
            "misses": getattr(self, "misses", 0),
            "hit_rate": (getattr(self, "hits", 0) / total) if total else 0.0,
            "size": len(getattr(self, "_store", getattr(self, "data", {})) or {}),
        }

semantic_cache = LLMSemanticCache(
    ttl=float(__import__("os").getenv("AURA_LLM_CACHE_TTL_SEC", "45")),
    maxsize=int(__import__("os").getenv("AURA_LLM_CACHE_MAX_ENTRIES", "512")),
)
# Alias nominal usado pelo pacote v12.7.3 e por integrações futuras.
LLM_CACHE = semantic_cache
