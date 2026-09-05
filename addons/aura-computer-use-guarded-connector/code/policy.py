"""Política fail-closed do conector Computer Use."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "manifest.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be object")
    return data


@dataclass(frozen=True)
class GuardedPolicy:
    computer_use_enabled: bool = False
    execution_allowed: bool = False
    approval_required: bool = True
    network_allowed: bool = False
    authenticated_profiles_allowed: bool = False
    scheduler_enabled: bool = False
    yolo_mode_allowed: bool = False
    unrestricted_mode_allowed: bool = False

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, Any] | None = None) -> "GuardedPolicy":
        m = dict(manifest or load_manifest())
        p = dict(m.get("policies") or {})
        return cls(
            computer_use_enabled=bool(p.get("computer_use_enabled", False)),
            execution_allowed=bool(p.get("execution_allowed", False)),
            approval_required=bool(p.get("approval_required", True)),
            network_allowed=bool(p.get("network_allowed", False)),
            authenticated_profiles_allowed=bool(p.get("authenticated_profiles_allowed", False)),
            scheduler_enabled=bool(p.get("scheduler_enabled", False)),
            yolo_mode_allowed=bool(p.get("yolo_mode_allowed", False)),
            unrestricted_mode_allowed=bool(p.get("unrestricted_mode_allowed", False)),
        )

    def assert_inert(self) -> None:
        if self.computer_use_enabled:
            raise RuntimeError("computer_use_enabled must be false at install stage")
        if self.execution_allowed:
            raise RuntimeError("execution_allowed must be false")
        if self.network_allowed:
            raise RuntimeError("network_allowed must be false")
        if not self.approval_required:
            raise RuntimeError("approval_required must be true")
        if self.yolo_mode_allowed or self.unrestricted_mode_allowed:
            raise RuntimeError("yolo/unrestricted modes are forbidden")
