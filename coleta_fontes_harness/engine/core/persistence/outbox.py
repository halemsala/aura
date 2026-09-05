from __future__ import annotations
import json, os
from pathlib import Path
from threading import Lock
from typing import Optional

class DurableOutbox:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")

    def rotate_for_replay(self) -> Optional[Path]:
        with self._lock:
            if not self.path.exists():
                return None
            replay = self.path.with_suffix(self.path.suffix + ".replay")
            os.replace(self.path, replay)
            return replay
