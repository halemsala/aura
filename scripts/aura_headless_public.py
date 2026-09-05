# -*- coding: utf-8 -*-
"""Headless opcional: abre/le paginas PUBLICAS. Nao substitui ui/state nem SokkerPRO F2."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
OUT = ROOT / "logs_supervisor" / "headless_public"
ALLOW_HOSTS = {
    "www.sokkerpro.com", "sokkerpro.com",
    "www.flashscore.com", "flashscore.com",
    "www.sofascore.com", "sofascore.com",
    "www.google.com", "google.com",
    "en.wikipedia.org", "wikipedia.org",
}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t:
                self._chunks.append(t)

    def text(self, max_chars=4000):
        joined = " ".join(self._chunks)
        joined = re.sub(r"\s+", " ", joined).strip()
        return joined[:max_chars]


def _host_ok(url: str) -> bool:
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        return False
    host = (u.hostname or "").lower()
    if host in ALLOW_HOSTS:
        return True
    # subdominios explicitamente publicos comuns
    for h in ALLOW_HOSTS:
        if host.endswith("." + h):
            return True
    return False


def fetch_public(url: str, timeout: float = 12.0) -> dict:
    url = (url or "").strip()
    if not url.startswith("http"):
        url = "https://" + url
    if not _host_ok(url):
        return {
            "ok": False,
            "error": "host nao esta na allowlist publica",
            "url": url,
            "hint": "Hosts: sokkerpro, flashscore, sofascore, google, wikipedia. Feed do jogo continua F2/ui/state.",
        }
    try:
        req = Request(url, headers={
            "User-Agent": "AURA-QUANT-X-HeadlessPublic/1.0 (+paper-trade; local operator)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            final = resp.geturl()
            status = resp.status
        text = ""
        title = ""
        if "html" in ctype.lower() or raw[:200].lower().find(b"<html") >= 0:
            html = raw.decode("utf-8", "replace")
            mt = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = re.sub(r"\s+", " ", mt.group(1)).strip() if mt else ""
            p = _TextExtractor()
            try:
                p.feed(html)
                text = p.text(5000)
            except Exception:
                text = re.sub(r"<[^>]+>", " ", html)
                text = re.sub(r"\s+", " ", text)[:5000]
        else:
            text = raw[:2000].decode("utf-8", "replace")
        OUT.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        meta = {
            "ok": True,
            "status": status,
            "url": url,
            "final_url": final,
            "title": title,
            "content_type": ctype,
            "text_preview": text[:2000],
            "ts": stamp,
            "note": "Headless publico apenas. NAO substitui GET :8765/api/ui/state nem Desktop F2.",
        }
        (OUT / f"fetch_{stamp}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300], "url": url}


def summarize_fetch(meta: dict) -> str:
    if not meta.get("ok"):
        return f"Headless falhou: {meta.get('error')} | {meta.get('url')} | {meta.get('hint','')}"
    return (
        f"Headless OK {meta.get('status')} — {meta.get('title') or meta.get('url')}\n"
        f"Preview: {(meta.get('text_preview') or '')[:700]}\n"
        f"(Guardado em logs_supervisor/headless_public/) Feed oficial do jogo = Desktop F2 → ui/state."
    )


if __name__ == "__main__":
    import sys
    u = sys.argv[1] if len(sys.argv) > 1 else "https://www.google.com"
    print(summarize_fetch(fetch_public(u)))
