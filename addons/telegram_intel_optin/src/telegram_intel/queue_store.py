"""Local tip queue — pending, auto-sent, blocked; operator can flush later."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class TipQueue:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"items": []})

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"items": []}

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def enqueue(self, text: str, meta: dict[str, Any] | None = None, status: str = "pending") -> str:
        data = self._read()
        item_id = str(uuid.uuid4())[:12]
        data.setdefault("items", []).append(
            {
                "id": item_id,
                "text": text,
                "meta": meta or {},
                "status": status,
                "created_at": time.time(),
            }
        )
        # bound size
        if len(data["items"]) > 500:
            data["items"] = data["items"][-400:]
        self._write(data)
        return item_id

    def list(self, status: str | None = "pending") -> list[dict]:
        items = self._read().get("items") or []
        if status is None:
            return items
        return [i for i in items if i.get("status") == status]

    def set_status(self, item_id: str, status: str) -> bool:
        data = self._read()
        ok = False
        for i in data.get("items") or []:
            if i.get("id") == item_id:
                i["status"] = status
                ok = True
                break
        if ok:
            self._write(data)
        return ok
