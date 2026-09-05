#!/usr/bin/env python3
"""AURA Tools Control API — local only 127.0.0.1:8790 (paper-only side controls).

V37.3.37+ security & GPU monitoring enhancements:
- Optional shared token (AURA_CONTROL_TOKEN)
- Action audit log
- Richer VRAM snapshot (temp + recommendations)
- Origin / Host basic checks
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST, PORT = "127.0.0.1", 8790
ROOT = Path(os.environ.get("AURA_ROOT", r"C:\aura"))
if not (ROOT / "engine").exists():
    ROOT = Path(__file__).resolve().parents[1]

QUEUE = ROOT / "data" / "telegram_intel" / "tip_queue.json"
POLICY_STATE = ROOT / "data" / "telegram_intel" / "policy_state.json"
KILL = ROOT / "data" / "telegram_intel" / "kill_switch.on"
LAST_VETO = ROOT / "data" / "elite_squad" / "last_veto.json"
OPS_OUT = ROOT / "desktop" / "ui" / "matriz_v22" / "ops_status.json"
POLICY_EXAMPLE = ROOT / "addons" / "telegram_intel_optin" / "config" / "operator_publish_policy.example.json"
POLICY_LIVE = ROOT / "config" / "operator_publish_policy.json"
AUDIT_LOG = ROOT / "logs_supervisor" / "control_api_actions.jsonl"

CONTROL_TOKEN = os.environ.get("AURA_CONTROL_TOKEN", "").strip()

def system_metrics():
    try:
        from aura_system_metrics import collect
        return collect()
    except Exception:
        # try sibling
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from aura_system_metrics import collect
            return collect()
        except Exception as e:
            return {"ok": False, "error": str(e)}



def _load(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _audit(action: str, detail: dict | None = None) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "detail": detail or {},
            "paper_trade": True,
            "execution_allowed": False,
        }
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def vram_snapshot() -> dict:
    """Richer GPU snapshot (nvidia-smi)."""
    info = {"ok": False, "gpus": [], "recommendations": [], "hint": "nvidia-smi indisponivel"}
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0:
            return info
        gpus = []
        tips = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                used, total = float(parts[2]), float(parts[3])
                pct = round(100.0 * used / total, 1) if total else 0.0
                g = {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "mem_used_mb": used,
                    "mem_total_mb": total,
                    "mem_pct": pct,
                    "util_pct": float(parts[4]),
                    "temp_c": float(parts[5]),
                }
                gpus.append(g)
                if pct >= 85:
                    tips.append(f"GPU{g['index']}: VRAM CRÍTICA ({pct}%). Rode AURA_GROK_GPU_LIVRE.bat; evite XTTS+Ollama simultâneos.")
                elif pct >= 70:
                    tips.append(f"GPU{g['index']}: VRAM alta ({pct}%). Prefira voice on-demand ou fallback FAST.")
                else:
                    tips.append(f"GPU{g['index']}: VRAM OK ({pct}%).")
                if g["temp_c"] >= 80:
                    tips.append(f"GPU{g['index']}: temperatura elevada ({g['temp_c']}°C).")
        if not tips and gpus:
            tips.append("GPUs dentro de limites normais.")
        if not gpus:
            tips.append("nvidia-smi sem GPUs — verifique driver NVIDIA.")
        tips.append("Ollama não é terminado pelos BATs de limpeza AURA (por desenho).")
        info = {"ok": True, "gpus": gpus, "recommendations": tips, "hint": "ok"}
    except Exception as e:
        info["hint"] = str(e)
        info["recommendations"] = [f"Erro ao ler GPU: {e}"]
    return info


def refresh_ops() -> dict:
    script = ROOT / "scripts" / "aura_ops_status_write.py"
    if script.exists():
        try:
            subprocess.run(
                [os.environ.get("AURA_PYTHON") or "python3", str(script)],
                cwd=str(ROOT),
                timeout=20,
                capture_output=True,
            )
        except Exception:
            pass
    ops = _load(OPS_OUT, {})
    # Enrich with live VRAM even if ops script is old
    if "vram" not in ops or not ops.get("vram", {}).get("ok"):
        ops["vram"] = vram_snapshot()
    else:
        # merge recommendations if missing
        live = vram_snapshot()
        if live.get("ok"):
            ops["vram"] = live
    return ops


def queue_counts() -> dict:
    items = _load(QUEUE, {"items": []}).get("items") or []
    counts = {"pending": 0, "sent": 0, "blocked": 0, "dry_run": 0, "failed": 0}
    for it in items:
        st = str(it.get("status") or "pending")
        counts[st] = counts.get(st, 0) + 1
    recent = sorted(items, key=lambda x: x.get("created_at") or 0, reverse=True)[:12]
    return {"counts": counts, "total": len(items), "recent": recent}


def agents_snapshot() -> dict:
    enabled_dir = ROOT / "agents" / "ENABLED"
    enabled = []
    if enabled_dir.exists():
        enabled = sorted([p.name for p in enabled_dir.glob("*.enabled")])
    elite = ROOT / "engine" / "agents" / "elite_squad"
    return {
        "enabled_count": len(enabled),
        "enabled_sample": enabled[:40],
        "elite_squad_present": elite.exists(),
        "last_veto": _load(LAST_VETO, {}),
        "paper_trade": True,
        "execution_allowed": False,
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "null")  # tighter than *
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-AURA-Token")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_token(self) -> bool:
        if not CONTROL_TOKEN:
            return True
        tok = self.headers.get("X-AURA-Token") or ""
        return tok == CONTROL_TOKEN

    def _local_only(self) -> bool:
        # Extra guard: Host header should be localhost / 127.0.0.1
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("127.0.0.1", "localhost", "")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if not self._local_only():
            return self._json(403, {"ok": False, "error": "local_only"})
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            return self._json(200, {
                "ok": True,
                "service": "aura-tools-control",
                "port": PORT,
                "paper_trade": True,
                "execution_allowed": False,
                "token_required": bool(CONTROL_TOKEN),
            })
        if path == "/api/status":
            ops = refresh_ops()
            return self._json(200, {
                "ok": True,
                "ops": ops,
                "telegram": queue_counts(),
                "kill_switch": KILL.exists(),
                "agents": agents_snapshot(),
                "policy_exists": POLICY_LIVE.exists() or POLICY_EXAMPLE.exists(),
                "vram": ops.get("vram") or vram_snapshot(),
                "system": system_metrics(),
            })
        if path == "/api/queue":
            return self._json(200, {"ok": True, **queue_counts()})
        if path == "/api/agents":
            return self._json(200, {"ok": True, **agents_snapshot()})
        if path == "/api/vram":
            return self._json(200, {"ok": True, "vram": vram_snapshot()})
        if path == "/api/system":
            return self._json(200, {"ok": True, **system_metrics()})
        if path == "/api/reports":
            # list recent reports under logs_supervisor and engine/artifacts
            reports = []
            for base in [ROOT / "logs_supervisor", ROOT / "engine" / "artifacts", ROOT / "reports"]:
                if base.exists():
                    for p in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
                        reports.append({"name": p.name, "path": str(p), "mtime": p.stat().st_mtime, "size": p.stat().st_size})
                    for p in sorted(base.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                        reports.append({"name": p.name, "path": str(p), "mtime": p.stat().st_mtime, "size": p.stat().st_size})
                    for p in sorted(base.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                        reports.append({"name": p.name, "path": str(p), "mtime": p.stat().st_mtime, "size": p.stat().st_size})
            reports = sorted(reports, key=lambda x: x["mtime"], reverse=True)[:30]
            return self._json(200, {"ok": True, "reports": reports})
        if path == "/api/policy":
            pol = _load(POLICY_LIVE, None) or _load(POLICY_EXAMPLE, {})
            return self._json(200, {
                "ok": True,
                "policy": pol,
                "live_file": str(POLICY_LIVE),
                "using_example": not POLICY_LIVE.exists(),
            })
        return self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if not self._local_only():
            return self._json(403, {"ok": False, "error": "local_only"})
        if not self._check_token():
            _audit("auth_fail", {"path": self.path})
            return self._json(401, {"ok": False, "error": "invalid_or_missing_token"})

        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}

        if path == "/api/kill_switch":
            on = bool(data.get("on", True))
            if on:
                KILL.parent.mkdir(parents=True, exist_ok=True)
                KILL.write_text("1", encoding="utf-8")
            else:
                if KILL.exists():
                    KILL.unlink()
            refresh_ops()
            _audit("kill_switch", {"on": on})
            return self._json(200, {"ok": True, "kill_switch": on})

        if path == "/api/queue/clear_pending":
            q = _load(QUEUE, {"items": []})
            items = q.get("items") or []
            kept = [i for i in items if i.get("status") != "pending"]
            removed = len(items) - len(kept)
            _save(QUEUE, {"items": kept})
            refresh_ops()
            _audit("clear_pending", {"removed": removed})
            return self._json(200, {"ok": True, "removed_pending": removed})

        if path == "/api/queue/mark":
            item_id = str(data.get("id") or "")
            status = str(data.get("status") or "pending")
            q = _load(QUEUE, {"items": []})
            ok = False
            for i in q.get("items") or []:
                if i.get("id") == item_id:
                    i["status"] = status
                    ok = True
                    break
            if ok:
                _save(QUEUE, q)
                refresh_ops()
            _audit("queue_mark", {"id": item_id, "status": status, "ok": ok})
            return self._json(200, {"ok": ok, "id": item_id, "status": status})

        if path == "/api/session/grant":
            hours = float(data.get("hours") or 12)
            hours = max(1.0, min(72.0, hours))
            st = _load(POLICY_STATE, {})
            st["session_until"] = time.time() + hours * 3600
            _save(POLICY_STATE, st)
            refresh_ops()
            _audit("session_grant", {"hours": hours})
            return self._json(200, {"ok": True, "session_until": st["session_until"], "hours": hours})

        if path == "/api/session/revoke":
            st = _load(POLICY_STATE, {})
            st["session_until"] = 0
            _save(POLICY_STATE, st)
            refresh_ops()
            _audit("session_revoke", {})
            return self._json(200, {"ok": True, "session_until": 0})

        if path == "/api/policy/enable_auto":
            pol = _load(POLICY_LIVE, None) or _load(POLICY_EXAMPLE, {})
            pol["enabled"] = bool(data.get("enabled", True))
            auto = pol.get("auto_publish") or {}
            if "auto_enabled" in data:
                auto["enabled"] = bool(data["auto_enabled"])
            pol["auto_publish"] = auto
            _save(POLICY_LIVE, pol)
            _audit("policy_enable_auto", {"enabled": pol["enabled"], "auto": auto.get("enabled")})
            return self._json(200, {"ok": True, "policy": pol})

        if path == "/api/refresh":
            ops = refresh_ops()
            return self._json(200, {"ok": True, "ops": ops})

        if path == "/api/elite/demo_veto":
            payload = {
                "verdict": data.get("verdict", "VETOED"),
                "effective_decision": data.get("effective_decision", "AGUARDA"),
                "reasons": data.get("reasons") or ["Demo UI — paper only"],
                "paper_trade": True,
                "execution_allowed": False,
                "at": time.time(),
            }
            _save(LAST_VETO, payload)
            refresh_ops()
            _audit("demo_veto", payload)
            return self._json(200, {"ok": True, "last_veto": payload})

        return self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt, *args):
        return


def main():
    httpd = HTTPServer((HOST, PORT), Handler)
    print(f"AURA Tools Control API http://{HOST}:{PORT} root={ROOT} token_required={bool(CONTROL_TOKEN)}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
