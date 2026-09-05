"""Pesquisa skills locais e sugere URLs de aprendizagem. Não instala nada sozinho."""
import re
from pathlib import Path
from urllib.parse import quote_plus

from .. import paths
from ..registry import ToolSpec, register
from ..validators import ValidationError

SKILLS_ROOT = paths.PROJECT_ROOT / "skills"


def _v_search(args) -> dict:
    q = str((args or {}).get("query") or (args or {}).get("q") or "").strip()
    if not q or len(q) > 200:
        raise ValidationError("query vazia ou demasiado longa")
    return {"query": q}


def search_skill(args, ctx) -> dict:
    a = _v_search(args)
    q = a["query"]
    tokens = [t for t in re.split(r"\W+", q.lower()) if len(t) > 2]
    hits = []
    if SKILLS_ROOT.exists():
        for p in SKILLS_ROOT.rglob("SKILL.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                continue
            hay = (p.as_posix() + "\n" + text).lower()
            score = sum(1 for t in tokens if t in hay)
            if score:
                hits.append({"path": str(p), "score": score, "preview": text[:280]})
    hits.sort(key=lambda x: -x["score"])
    urls = [
        "https://www.google.com/search?q=" + quote_plus(q + " tutorial criativo"),
        "https://www.google.com/search?q=" + quote_plus(q + " photoshop skill"),
    ]
    return {
        "query": q,
        "local_skills": hits[:8],
        "suggested_urls": urls,
        "nota": "não abri páginas. Diz 'Alfred, abre <url>' ou 'abre pesquisas sobre …' se quiseres abrir.",
    }


register(ToolSpec("search_skill", search_skill, _v_search, risk="low", mutating=False,
                  summary="Pesquisa skills locais e sugere URLs. Não abre browser sozinho."))
