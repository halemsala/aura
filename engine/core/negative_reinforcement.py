"""Memória local de padrões perdedores; não executa ações externas."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


class NegativeReinforcementMemory:
    def __init__(self, file_path: str | Path = "data/negative_patterns.json") -> None:
        self.file_path = Path(file_path)
        self._blacklist: set[str] = set()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            self._blacklist = set(str(x) for x in data) if isinstance(data, list) else set()
        except (OSError, ValueError, TypeError):
            self._blacklist = set()

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.file_path.name + ".", dir=self.file_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(sorted(self._blacklist), handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.file_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _hash_features(features: Dict[str, Any]) -> str:
        key = "|".join(str(features.get(k, "")) for k in ("minute", "score", "wom_trend", "phase"))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def is_blacklisted(self, features: Dict[str, Any]) -> bool:
        return self._hash_features(features) in self._blacklist

    def record_loss(self, features: Dict[str, Any]) -> None:
        self._blacklist.add(self._hash_features(features))
        self._save()

    def status(self) -> dict:
        return {"patterns": len(self._blacklist), "paper_only": True,
                "execution_allowed": False}


__all__ = ["NegativeReinforcementMemory"]
