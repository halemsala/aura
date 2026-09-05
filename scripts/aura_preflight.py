#!/usr/bin/env python3
"""Read-only preflight for an AURA Quant-X distribution.

Returns 0 when blocking checks pass, 1 when a blocking check fails. Warnings are
reported but do not fail. No process is stopped and no file is modified.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

REQUIRED_FILES = (
    "AURA_INSTALAR_E_INICIAR_TUDO.bat",
    "PACKAGE_RELEASE.txt",
    "desktop/aura_self_test.py",
    "bridge/jarvis_voice_server.py",
    "bridge/voice_preflight.py",
    "bridge/jarvis/config.yaml",
)
OPTIONAL_SERVICE_FILES = (
    "engine/server.py",
    "bridge/server.py",
)
PORTS = (8080, 8765, 8099)
_PAPER_TRADE_MARKER = re.compile(r"paper[\s_-]*trade|paper_trade_only", re.I)
_LIVE_EXECUTION_MARKER = re.compile(r"(?:send|place|submit|execute)\s+(?:a\s+)?(?:live|real)\s+order|broker\.(?:submit|send)|live_order", re.I)


def check(name: str, ok: bool, detail: str, *, warning: bool = False) -> dict[str, Any]:
    return {"name": name, "ok": ok, "warning": warning, "detail": detail}


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def run(root: Path) -> tuple[list[dict[str, Any]], int]:
    checks: list[dict[str, Any]] = []
    checks.append(check("root_exists", root.is_dir(), str(root)))
    for relative in REQUIRED_FILES:
        path = root / relative
        checks.append(check(f"required:{relative}", path.is_file(), "present" if path.is_file() else "missing"))
    for relative in OPTIONAL_SERVICE_FILES:
        path = root / relative
        checks.append(check(f"optional:{relative}", path.is_file(), "present" if path.is_file() else "not found in this layout", warning=not path.is_file()))

    release = root / "PACKAGE_RELEASE.txt"
    if release.is_file():
        marker = release.read_text(encoding="utf-8", errors="replace").strip()
        checks.append(check("release_marker", bool(marker), marker or "empty"))
    else:
        marker = ""

    bat_files = sorted(root.rglob("*.bat")) if root.is_dir() else []
    bad_bat = []
    for path in bat_files:
        raw = path.read_bytes()
        normalized = raw.replace(b"\r\n", b"")
        if b"\n" in normalized or b"\r" in normalized:
            bad_bat.append(str(path.relative_to(root)))
    checks.append(check("bat_crlf", not bad_bat, ", ".join(bad_bat) if bad_bat else f"{len(bat_files)} BAT(s) in CRLF"))

    config = root / "bridge/jarvis/config.yaml"
    config_text = config.read_text(encoding="utf-8", errors="replace") if config.is_file() else ""
    checks.append(check("male_voice_config", "pt-BR-AntonioNeural" in config_text and "xtts_enabled: false" in config_text, "AntonioNeural + XTTS disabled"))
    checks.append(check("no_female_voice_config", "Francisca" not in config_text, "no Francisca in canonical config"))

    paper_files = [root / "bridge/server.py", root / "engine/server.py", root / "desktop/aura_self_test.py"]
    paper_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in paper_files if p.is_file())
    paper_guard_ok = bool(_PAPER_TRADE_MARKER.search(paper_text)) and not _LIVE_EXECUTION_MARKER.search(paper_text)
    checks.append(check("paper_trade_guard", paper_guard_ok, "paper-trade marker present and no live-order execution marker"))

    py_ok = sys.version_info >= (3, 10)
    checks.append(check("python_version", py_ok, platform.python_version()))
    try:
        free_gb = shutil.disk_usage(root).free / (1024**3)
        checks.append(check("disk_space", free_gb >= 5, f"{free_gb:.2f} GiB free", warning=free_gb < 5))
    except OSError as exc:
        checks.append(check("disk_space", False, f"disk usage unavailable: {exc}"))

    occupied = [port for port in PORTS if port_open(port)]
    checks.append(check("ports_free", not occupied, "free" if not occupied else f"occupied: {occupied}"))

    blocking = [item for item in checks if not item["ok"] and not item["warning"]]
    return checks, 1 if blocking else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    checks, rc = run(args.root.resolve())
    print(json.dumps({"ok": rc == 0, "checks": checks}, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
