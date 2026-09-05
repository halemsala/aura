#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hermes Sensors V10 — detecção por setor com parse JSON real (não string-contains)."""
from __future__ import annotations

import json
import os
import py_compile
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PORTS = {"bridge": 8080, "engine": 8765, "voice": 8099, "ollama": 11434, "dashboard": 3000}
CRITICAL_FILES = [
    "engine/server.py",
    "engine/grounding.py",
    "engine/features.py",
    "bridge/server.py",
]
STALE_SECONDS = 45


@dataclass
class Finding:
    sector: str
    code: str
    severity: str
    message: str
    fix_hint: str = ""
    auto_fixable: bool = False
    fixed: bool = False
    confidence: float = 0.5
    detail: Dict[str, Any] = field(default_factory=dict)
    source: str = "sensor"


def port_open(port: int, t: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=t):
            return True
    except OSError:
        return False


def http_get(url: str, t: float = 4.0) -> Tuple[int, Any]:
    try:
        req = Request(url, headers={"User-Agent": "Hermes/7.0"})
        with urlopen(req, timeout=t) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def compile_file(path: Path) -> Optional[str]:
    try:
        py_compile.compile(str(path), doraise=True)
        return None
    except Exception as e:
        return str(e)


def _view_from_state(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    snap = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    view = snap.get("view") if isinstance(snap, dict) and isinstance(snap.get("view"), dict) else {}
    if not view and isinstance(snap, dict):
        view = snap
    return view if isinstance(view, dict) else {}


def detect_all(root: Path, tier: str = "full") -> List[Finding]:
    """tier=fast|medium|full — menos HTTP no ciclo quente."""
    out: List[Finding] = []
    out.extend(_detect_codigo(root))
    out.extend(_detect_conexao())
    out.extend(_detect_seguranca())
    out.extend(_detect_captura(root))
    out.extend(_detect_extensao(root))
    if tier in ("medium", "full"):
        out.extend(_detect_servicos(root))
        out.extend(_detect_ui_state())
    if tier == "full":
        out.extend(_detect_codigo_drift(root))
        out.extend(_detect_ollama())
    return out


def _detect_codigo_drift(root: Path) -> List[Finding]:
    out: List[Finding] = []
    try:
        from hermes_auditor import audit_tree
        for hit in audit_tree(root):
            if hit.ok:
                out.append(Finding(
                    "codigo", f"AUDIT_OK_{hit.code}", "OK", hit.message, confidence=0.95,
                    detail={"file": hit.file}, source="auditor",
                ))
            else:
                out.append(Finding(
                    "codigo", f"CODE_DRIFT_{hit.code}", "HIGH", hit.message,
                    hit.hint, auto_fixable=False, confidence=0.86,
                    detail={"file": hit.file}, source="auditor",
                ))
    except Exception as e:
        out.append(Finding("codigo", "AUDITOR_FAIL", "LOW", str(e)[:80], confidence=0.4))
    return out


def _detect_codigo(root: Path) -> List[Finding]:
    out: List[Finding] = []
    for rel in CRITICAL_FILES:
        p = root / rel
        if not p.exists():
            out.append(Finding(
                "codigo", f"MISSING_{rel.replace('/', '_')}", "CRITICAL",
                f"Ausente {rel}", confidence=0.95,
            ))
            continue
        err = compile_file(p)
        if err:
            out.append(Finding(
                "codigo", f"SYNTAX_{p.name}", "CRITICAL", err[:160],
                "fix allowlisted + rollback", auto_fixable=True,
                confidence=0.9, detail={"file": str(p), "error": err},
            ))
        else:
            out.append(Finding("codigo", f"COMPILE_OK_{p.name}", "OK", f"{rel} OK", confidence=0.99))
    return out


def _detect_conexao() -> List[Finding]:
    out: List[Finding] = []
    for name, port in PORTS.items():
        if port_open(port):
            out.append(Finding("conexao", f"PORT_{port}", "OK", f"{name} LISTEN", confidence=0.99))
        else:
            if name == "dashboard":
                out.append(Finding(
                    "conexao", f"PORT_{port}_OFF", "LOW",
                    "dashboard Node OFF (opcional)", "iniciar-windows.bat",
                    confidence=0.7,
                ))
            elif name == "ollama":
                out.append(Finding(
                    "conexao", f"PORT_{port}_OFF", "HIGH",
                    "Ollama OFF", "LLM advisory only", confidence=0.85,
                ))
            else:
                sev = "CRITICAL" if name in ("bridge", "engine") else "HIGH"
                out.append(Finding(
                    "conexao", f"PORT_{port}_OFF", sev, f"{name} OFF",
                    f"safe_start_{name}", auto_fixable=True, confidence=0.95,
                ))
    return out


def _detect_servicos(root: Path) -> List[Finding]:
    out: List[Finding] = []
    checks = [
        ("Bridge", "http://127.0.0.1:8080/health", True),
        ("Engine", "http://127.0.0.1:8765/api/health", True),
        ("Voice", "http://127.0.0.1:8099/api/voice/health", False),
    ]
    for name, url, critical in checks:
        port = {"Bridge": 8080, "Engine": 8765, "Voice": 8099}[name]
        code, body = http_get(url)
        if code == 200:
            out.append(Finding("servicos", f"{name.upper()}_HEALTH", "OK", f"{name} OK", confidence=0.98))
        else:
            if port_open(port):
                out.append(Finding(
                    "servicos", f"{name.upper()}_ZOMBIE",
                    "CRITICAL" if critical else "HIGH",
                    f"{name} porta aberta mas health HTTP {code}",
                    "reiniciar processo", auto_fixable=True, confidence=0.88,
                    detail={"code": code, "body": str(body)[:120]},
                ))
            else:
                out.append(Finding(
                    "servicos", f"{name.upper()}_DOWN",
                    "CRITICAL" if critical else "HIGH",
                    f"{name} DOWN", auto_fixable=True, confidence=0.9,
                ))

    venv = root / "engine" / "venv" / "Scripts" / "python.exe"
    if venv.exists():
        out.append(Finding("servicos", "VENV_OK", "OK", "venv OK", confidence=0.99))
        try:
            r = subprocess.run(
                [str(venv), "-c", "import fastapi,uvicorn,httpx,requests,pydantic,psutil; print('OK')"],
                capture_output=True, text=True, timeout=12,
            )
            if "OK" not in (r.stdout or ""):
                out.append(Finding(
                    "servicos", "DEPS_MISSING", "HIGH", "deps em falta",
                    auto_fixable=True, confidence=0.9,
                ))
            else:
                out.append(Finding("servicos", "DEPS_OK", "OK", "deps OK", confidence=0.97))
        except Exception:
            pass
    else:
        out.append(Finding(
            "servicos", "VENV_MISSING", "CRITICAL", "venv ausente",
            auto_fixable=True, confidence=0.95,
        ))
    return out


def _detect_captura(root: Path) -> List[Finding]:
    out: List[Finding] = []
    latest = root / "bridge" / "live_latest.json"
    if not latest.exists() or latest.stat().st_size < 10:
        out.append(Finding(
            "captura", "LIVE_LATEST_EMPTY", "HIGH", "live_latest vazio",
            "SokkerPRO live + extensão unpacked + F5", confidence=0.85,
        ))
        return out
    age = time.time() - latest.stat().st_mtime
    if age > STALE_SECONDS:
        out.append(Finding(
            "captura", "LIVE_STALE", "HIGH",
            f"live_latest com {int(age)}s (limite {STALE_SECONDS}s)",
            "Aba SokkerPRO inativa — não reinstalar",
            confidence=0.9, detail={"age_s": int(age)},
        ))
    try:
        data = json.loads(latest.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        out.append(Finding("captura", "LIVE_JSON_INVALID", "HIGH", str(e)[:80], confidence=0.8))
        return out
    if not isinstance(data, dict):
        out.append(Finding("captura", "LIVE_JSON_INVALID", "HIGH", "live_latest não é objecto", confidence=0.8))
        return out
    home = data.get("home") or data.get("home_team")
    away = data.get("away") or data.get("away_team")
    if home and away:
        msg = f"{home} x {away}"
        if age <= STALE_SECONDS:
            out.append(Finding("captura", "LIVE_DATA_OK", "OK", msg, confidence=0.92,
                               detail={"home": home, "away": away, "age_s": int(age)}))
        else:
            out.append(Finding("captura", "LIVE_DATA_STALE_TEAMS", "MEDIUM",
                               f"{msg} mas stale {int(age)}s", confidence=0.7))
    else:
        out.append(Finding("captura", "LIVE_DATA_PARTIAL", "MEDIUM", "sem times", confidence=0.7))
    return out


def _detect_ui_state() -> List[Finding]:
    out: List[Finding] = []
    if not port_open(8765):
        out.append(Finding(
            "captura", "UI_STATE_UNREACHABLE", "HIGH",
            "Engine OFF — ui/state indisponível", confidence=0.8,
        ))
        return out
    code, payload = http_get("http://127.0.0.1:8765/api/ui/state")
    if code != 200:
        out.append(Finding(
            "captura", "UI_STATE_HTTP", "HIGH",
            f"ui/state HTTP {code}", confidence=0.85, detail={"code": code},
        ))
        return out
    view = _view_from_state(payload)
    home = view.get("home") or view.get("home_team")
    away = view.get("away") or view.get("away_team")
    if isinstance(home, list) and home:
        home = home[0]
    if isinstance(away, list) and away:
        away = away[0]
    events = []
    if isinstance(payload, dict):
        snap = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
        if isinstance(snap, dict):
            events = snap.get("corner_events") or view.get("corner_events") or []
    if home and away:
        out.append(Finding(
            "captura", "UI_STATE_VIEW_OK", "OK",
            f"view {home} x {away}", confidence=0.93,
            detail={"home": home, "away": away, "events": len(events) if isinstance(events, list) else 0},
        ))
    else:
        out.append(Finding(
            "captura", "UI_STATE_NO_VIEW", "HIGH",
            "ui/state 200 sem view.home — captura/grounding",
            "Lift view em server.py; grounding lê snap/view",
            confidence=0.8,
        ))
    if isinstance(events, list) and events:
        out.append(Finding(
            "captura", "CORNER_EVENTS_OK", "OK",
            f"{len(events)} corner_events", confidence=0.9,
        ))
    else:
        out.append(Finding(
            "captura", "CORNER_EVENTS_EMPTY", "MEDIUM",
            "corner_events vazio (pode ser início de jogo)",
            confidence=0.6,
        ))

    if isinstance(payload, dict):
        grounding = payload.get("grounding") if isinstance(payload.get("grounding"), dict) else {}
        missing = grounding.get("missing") if grounding else None
        if isinstance(missing, list) and missing:
            out.append(Finding(
                "captura", "GROUNDING_MISSING", "MEDIUM",
                f"grounding.missing={missing[:6]}",
                "grounding.py deve ler snap/view + corner_events",
                confidence=0.75, detail={"missing": missing[:10]},
            ))
        blocked = str(payload.get("status") or payload.get("gate") or "")
        blob = json.dumps(payload)[:2000] if isinstance(payload, dict) else ""
        if "BLOCKED_BY_DATA" in blob or "BLOCKED_BY_DATA" in blocked:
            out.append(Finding(
                "captura", "BLOCKED_BY_DATA", "INFO",
                "fail-closed paper-trade (não é crash)",
                "odds.corners=[] ≠ sistema morto", confidence=0.8,
            ))
        ids = set()
        for key in ("fixtureId", "fixture_id", "id"):
            if isinstance(payload.get(key), (str, int)):
                ids.add(str(payload.get(key)))
        snap = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        if isinstance(snap, dict):
            for key in ("fixtureId", "fixture_id", "id"):
                if isinstance(snap.get(key), (str, int)):
                    ids.add(str(snap.get(key)))
        if len(ids) >= 2:
            out.append(Finding(
                "captura", "FIXTURE_ALIAS", "LOW",
                f"vários fixtureIds {sorted(ids)[:3]} — usar times+minuto do view",
                "remember canónico", confidence=0.7, detail={"ids": sorted(ids)},
            ))
    return out


def _detect_seguranca() -> List[Finding]:
    out: List[Finding] = []
    paper = os.environ.get("PAPER_TRADE", "true").lower()
    exe = os.environ.get("EXECUTION_ALLOWED", "false").lower()
    if paper != "true":
        out.append(Finding(
            "seguranca", "PAPER_TRADE_VIOLATION", "CRITICAL",
            f"PAPER={paper}", auto_fixable=True, confidence=0.99,
        ))
    else:
        out.append(Finding("seguranca", "PAPER_TRADE_OK", "OK", "paper OK", confidence=0.99))
    if exe != "false":
        out.append(Finding(
            "seguranca", "EXECUTION_ALLOWED_VIOLATION", "CRITICAL",
            f"EXEC={exe}", auto_fixable=True, confidence=0.99,
        ))
    else:
        out.append(Finding("seguranca", "EXECUTION_ALLOWED_OK", "OK", "exec false OK", confidence=0.99))
    return out


def _detect_ollama() -> List[Finding]:
    if port_open(11434):
        code, body = http_get("http://127.0.0.1:11434/api/tags", t=3.0)
        if code == 200 and isinstance(body, dict):
            models = [m.get("name", "") for m in body.get("models", []) if isinstance(m, dict)]
            return [Finding(
                "ollama", "OLLAMA_PORT", "OK",
                f"Ollama UP models={models[:4] or 'n/d'}", confidence=0.95,
                detail={"models": models},
            )]
        return [Finding("ollama", "OLLAMA_PORT", "OK", "Ollama UP", confidence=0.9)]
    return [Finding("ollama", "OLLAMA_OFF", "HIGH", "Ollama OFF", confidence=0.85)]


def _detect_extensao(root: Path) -> List[Finding]:
    ext = root / "extensao"
    man = ext / "manifest.json"
    if not ext.is_dir():
        return [Finding(
            "captura", "EXTENSION_MISSING", "HIGH",
            "pasta extensao ausente",
            "Carregar unpacked pasta extensao no Chrome", confidence=0.8,
        )]
    if not man.exists():
        return [Finding(
            "captura", "EXTENSION_NO_MANIFEST", "MEDIUM",
            "pasta extensao sem manifest.json", confidence=0.7,
        )]
    try:
        data = json.loads(man.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return [Finding("captura", "EXTENSION_MANIFEST_INVALID", "HIGH", str(e)[:80], confidence=0.75)]
    ver = data.get("manifest_version")
    matches = str(data)
    ok_bits = []
    if ver == 3:
        ok_bits.append("mv3")
    else:
        return [Finding("captura", "EXTENSION_NOT_MV3", "MEDIUM",
                        f"manifest_version={ver}", "Extensão deve ser MV3", confidence=0.7)]
    if "sokkerpro" in matches.lower():
        ok_bits.append("sokkerpro")
    return [Finding("captura", "EXTENSION_PRESENT", "OK",
                    "extensao " + "+".join(ok_bits), confidence=0.95,
                    detail={"manifest_version": ver})]
