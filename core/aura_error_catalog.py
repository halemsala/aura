#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ErrorCatalog — casa sintomas ↔ codigos, executa fixes, mede cobertura, aprende."""
from __future__ import annotations
import json, re, time, hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

class ErrorCatalog:
    def __init__(self, root: str):
        self.root = Path(root)
        # catalog pode estar em core/ na raiz AURA ou junto deste ficheiro
        candidates = [
            self.root / "core" / "aura_error_catalog.json",
            Path(__file__).resolve().parent / "aura_error_catalog.json",
        ]
        self.catalog_path = next((p for p in candidates if p.exists()), candidates[0])
        self.triage_path = self.root / "logs_supervisor" / "catalog_triage.jsonl"
        self.match_log = self.root / "logs_supervisor" / "catalog_matches.jsonl"
        self.triage_path.parent.mkdir(parents=True, exist_ok=True)
        self.entries: Dict[str, dict] = {}
        self._index: List[tuple] = []
        self._handlers: Dict[str, Callable] = {}
        self.load()

    def load(self):
        if not self.catalog_path.exists():
            self.entries, self._index = {}, []
            return
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.entries = {e["code"]: e for e in data.get("entries", []) if isinstance(e, dict) and e.get("code")}
        self._index = []
        for code, e in self.entries.items():
            for s in e.get("symptoms", []):
                try:
                    self._index.append((re.compile(s, re.IGNORECASE), code))
                except re.error:
                    continue

    def add(self, entry: dict):
        entry["added_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.entries[entry["code"]] = entry
        data = {"version": int(time.time()), "entries": list(self.entries.values())}
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.load()

    def register_fix(self, code: str, fn: Callable):
        self._handlers[code] = fn

    def match_text(self, text: str) -> List[dict]:
        low = (text or "")
        codes = {code for rx, code in self._index if rx.search(low)}
        hits = [self.entries[c] for c in codes if c in self.entries]
        return sorted(hits, key=lambda e: SEV_ORDER.get(e.get("severity", "low"), 3))

    def diagnose(self, evidence: Dict[str, Any]) -> dict:
        blob = "\n".join(str(v) for v in evidence.values())
        hits = self.match_text(blob)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not hits:
            tid = self._record_unknown(blob, evidence)
            self._log_match(None, ts)
            return {
                "code": f"E-NEW-{tid}", "known": False,
                "message": "Erro NOVO capturado para triagem. Contexto salvo.",
                "triage_id": tid,
            }
        primary = hits[0]
        self._log_match(primary["code"], ts)
        return {
            "code": primary["code"], "known": True,
            "title": primary["title"], "severity": primary.get("severity", "medium"),
            "location": primary.get("location", {}),
            "cause": primary.get("cause", ""),
            "fix": primary.get("fix", {}),
            "other_matches": [h["code"] for h in hits[1:6]],
            "commands": [h.get("fix", {}).get("action", "") for h in hits if h.get("fix")],
            "status": primary.get("status"),
        }

    def apply_fix(self, code: str, dry_run: bool = False) -> dict:
        code = (code or "").upper().strip()
        e = self.entries.get(code)
        if not e:
            return {"ok": False, "error": f"codigo {code} nao existe no catalogo"}
        fx = e.get("fix", {}) or {}
        if dry_run:
            return {"ok": True, "dry_run": True, "would_do": fx.get("action")}
        if code in self._handlers:
            try:
                return {"ok": True, "result": self._handlers[code]()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        # handler name mapping
        hname = fx.get("handler")
        if hname and hname in self._handlers:
            try:
                return {"ok": True, "result": self._handlers[hname]()}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        return {"ok": False, "error": "sem handler automatico", "manual": fx.get("action", "")}

    def _record_unknown(self, blob: str, evidence: dict) -> str:
        tid = hashlib.sha1(blob.encode("utf-8", errors="ignore")).hexdigest()[:6]
        rec = {
            "id": tid,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "context": {k: str(v)[:3000] for k, v in evidence.items()},
        }
        with self.triage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return tid

    def _log_match(self, code: Optional[str], ts: str):
        with self.match_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "code": code}) + "\n")

    def coverage(self, hours: int = 24) -> float:
        cutoff = time.time() - hours * 3600
        matched = unknown = 0
        if self.match_log.exists():
            for ln in self.match_log.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    r = json.loads(ln)
                    ts = time.mktime(time.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ"))
                    if ts >= cutoff:
                        if r.get("code"):
                            matched += 1
                        else:
                            unknown += 1
                except Exception:
                    continue
        total = matched + unknown
        return round(100.0 * matched / total, 1) if total else 100.0

    def pending_triage(self) -> List[dict]:
        if not self.triage_path.exists():
            return []
        out = []
        for l in self.triage_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]:
            if l.strip():
                try:
                    out.append(json.loads(l))
                except Exception:
                    pass
        return out

    @staticmethod
    def format_for_chat(diag: dict) -> str:
        if not diag.get("known"):
            return (
                f"NOVO {diag.get('code')} — erro capturado para triagem.\n"
                "O contexto foi salvo. Na proxima ocorrencia ja pode ser catalogado."
            )
        loc = diag.get("location", {}) or {}
        onde = loc.get("file") or loc.get("service") or "?"
        porta = f" (porta {loc['port']})" if loc.get("port") else ""
        fx = (diag.get("fix") or {}).get("action", "")
        emoji = {"critical": "[CRIT]", "high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(
            diag.get("severity", ""), "[?]"
        )
        out = [
            f"{emoji} {diag['code']} · {diag.get('title', '')}",
            f"  Onde: {onde}{porta}",
            f"  Causa: {diag.get('cause', '?')}",
            f"  Corrigir: \"{fx}\" (ou: fix {diag['code']})",
        ]
        if diag.get("other_matches"):
            out.append(f"  Tambem: {', '.join(diag['other_matches'])}")
        if diag.get("status") == "patched":
            out.append(f"  Status: ja patched em {diag.get('patched_in', '?')}")
        return "\n".join(out)


if __name__ == "__main__":
    import os
    root = os.getenv("AURA_ROOT", ".")
    cat = ErrorCatalog(root)
    print(f"entries={len(cat.entries)} path={cat.catalog_path}")
    d = cat.diagnose({"port_status": "OFF 8765 engine off", "log": "engine down"})
    print(ErrorCatalog.format_for_chat(d))
