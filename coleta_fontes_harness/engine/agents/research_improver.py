#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
research_improver.py — o assistente PESQUISA para melhorar o AURA: repos
GitHub, papers arXiv e web viram conhecimento e PROPOSTAS numeradas.

O LOOP DE AUTO-MELHORIA CORRETO:
    1. PESQUISA — este modulo descobre candidatos em APIs publicas e resume.
    2. PROPOSTA — relevantes viram itens em engine/data/
       improvement_proposals.jsonl (status: proposta -> implementada/
       rejeitada).
    3. DECISAO HUMANA — voce escolhe; implementacao segue o protocolo de
       sempre: novo chat com o fonte na mesa, Grok instala, self-test valida.
    O assistente NAO edita o proprio engine (por desenho E por disciplina).

FONTES (GET publico, stdlib, sem token):
    GitHub Search API (~10 buscas/min) + README sob demanda.
    arXiv API (papers de modelagem; abstract entra direto no conhecimento).

CAMPANHAS PADRAO — roadmap real do AURA: conformal, poisson in-play,
whisper/VAD, ollama/tools, ffmpeg, marketing de produto analitico.

INTEGRACAO: hunks na resposta. Depende de web_knowledge.ToolKnowledge
(same dir) apenas para aprender — degrade honesto sem ele.

stdlib only. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import threading
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aura.research")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]
_PROPOSALS = _PROJ_ROOT / "engine" / "data" / "improvement_proposals.jsonl"


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_index(s: Any) -> Optional[int]:
    m = re.search(r"\d+", str(s or ""))
    return int(m.group()) if m else None


class _Http:
    """GET injetavel (testes sem rede). Nunca levanta — caller decide."""

    def __init__(self, fetch_fn: Optional[Callable] = None, timeout: float = 10.0):
        self._fetch = fetch_fn or self._default
        self.timeout = float(timeout)
        self.calls = 0

    def _default(self, url: str, headers: Dict[str, str]):
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()

    def get(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.calls += 1
        return self._fetch(url, headers or {})


class GithubSource:
    SEARCH = ("https://api.github.com/search/repositories?q=%s"
              "&sort=stars&order=desc&per_page=%d")
    README = "https://api.github.com/repos/%s/readme"

    def __init__(self, http: Optional[_Http] = None, min_interval: float = 7.0,
                 clock: Callable[[], float] = time.monotonic):
        self._http = http or _Http()
        self._min = float(min_interval)
        self._clock = clock
        self._last = -1e9
        self.stats = {"searches": 0, "readmes": 0,
                      "rate_blocked": 0, "failures": 0}

    def _throttle(self) -> Optional[str]:
        if self._clock() - self._last < self._min:
            return ("Sem token o GitHub permite cerca de 10 buscas por minuto; "
                    "aguarde alguns segundos e repita.")
        return None

    def search_repos(self, query: str, limit: int = 8) -> dict:
        if not (query or "").strip():
            return {"ok": False, "speech": "Diga o topico da pesquisa."}
        block = self._throttle()
        if block:
            self.stats["rate_blocked"] += 1
            return {"ok": False, "speech": block}
        self._last = self._clock()
        url = self.SEARCH % (urllib.parse.quote(query), max(1, min(limit, 20)))
        try:
            status, _h, body = self._http.get(url, {
                "Accept": "application/vnd.github+json",
                "User-Agent": "AURA-research/1.0"})
        except Exception as exc:
            self.stats["failures"] += 1
            return {"ok": False, "speech": "GitHub inacessivel: %s" % exc}
        if status == 403:
            self.stats["rate_blocked"] += 1
            return {"ok": False,
                    "speech": "Limite do GitHub atingido (sem token). Tente em alguns minutos."}
        if status != 200:
            return {"ok": False, "speech": "GitHub respondeu HTTP %s." % status}
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError:
            return {"ok": False, "speech": "Resposta ilegivel do GitHub."}
        items = data.get("items") or []
        self.stats["searches"] += 1
        findings = [{"kind": "repo", "title": str(it.get("full_name", "?")),
                     "url": str(it.get("html_url", "")),
                     "detail": "%s stars, %s — %s" % (
                         it.get("stargazers_count", 0),
                         it.get("language") or "linguagem n/d",
                         (it.get("description") or "")[:120])}
                    for it in items[:limit]]
        return {"ok": True, "findings": findings, "query": query}

    def fetch_readme(self, owner_repo: str) -> dict:
        ref = (owner_repo or "").strip().strip("/")
        if not ref or "/" not in ref:
            return {"ok": False, "speech": "Formato esperado: dono/repositorio."}
        try:
            status, _h, body = self._http.get(self.README % ref, {
                "Accept": "application/vnd.github+json",
                "User-Agent": "AURA-research/1.0"})
        except Exception as exc:
            self.stats["failures"] += 1
            return {"ok": False, "speech": "GitHub inacessivel: %s" % exc}
        if status == 404:
            return {"ok": False,
                    "speech": "Repositorio %s nao encontrado ou sem README." % ref}
        if status != 200:
            return {"ok": False, "speech": "GitHub respondeu HTTP %s." % status}
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
            text = base64.b64decode(data.get("content") or ""
                                    ).decode("utf-8", errors="replace")
        except Exception:
            return {"ok": False, "speech": "README ilegivel."}
        if not text.strip():
            return {"ok": False, "speech": "README vazio."}
        self.stats["readmes"] += 1
        return {"ok": True, "title": ref, "text": text[:300_000]}


class ArxivSource:
    API = ("http://export.arxiv.org/api/query?search_query=all:%s"
           "&start=0&max_results=%d")
    NS = "{http://www.w3.org/2005/Atom}"

    def __init__(self, http: Optional[_Http] = None, min_interval: float = 3.0,
                 clock: Callable[[], float] = time.monotonic):
        self._http = http or _Http()
        self._min = float(min_interval)
        self._clock = clock
        self._last = -1e9
        self.stats = {"searches": 0, "failures": 0}

    def search(self, query: str, limit: int = 6) -> dict:
        if not (query or "").strip():
            return {"ok": False, "speech": "Diga o topico da pesquisa."}
        if self._clock() - self._last < self._min:
            return {"ok": False,
                    "speech": "arXiv pede intervalo de 3s entre buscas; repita ja."}
        self._last = self._clock()
        url = self.API % (urllib.parse.quote(query), max(1, min(limit, 15)))
        try:
            status, _h, body = self._http.get(url, {})
        except Exception as exc:
            self.stats["failures"] += 1
            return {"ok": False, "speech": "arXiv inacessivel: %s" % exc}
        if status != 200:
            return {"ok": False, "speech": "arXiv respondeu HTTP %s." % status}
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return {"ok": False, "speech": "Resposta ilegivel do arXiv."}
        findings = []
        for entry in root.iter(self.NS + "entry"):
            title = " ".join((entry.findtext(self.NS + "title") or "").split())
            summary = " ".join((entry.findtext(self.NS + "summary") or "").split())
            url_e = ""
            for link in entry.iter(self.NS + "link"):
                if link.get("rel") == "alternate" and link.get("href"):
                    url_e = link.get("href")
                    break
            published = (entry.findtext(self.NS + "published") or "")[:10]
            findings.append({"kind": "paper", "title": title or "sem titulo",
                             "url": url_e,
                             "detail": "(%s) %s" % (published, summary[:180]),
                             "abstract": summary})
        self.stats["searches"] += 1
        return {"ok": True, "findings": findings[:limit], "query": query}


class ResearchImprover:
    CAMPAIGNS: Dict[str, str] = {
        "conformal": "conformal prediction online calibration",
        "poisson": "in-play football poisson corner model",
        "voz": "whisper streaming voice activity detection",
        "llm": "ollama local tool calling agent",
        "midia": "ffmpeg batch automation media",
        "marketing": "sports analytics product marketing subscription",
    }

    def __init__(self, kb: Any = None, github: Optional[GithubSource] = None,
                 arxiv: Optional[ArxivSource] = None,
                 proposals_path: Optional[Any] = None):
        self._lock = threading.RLock()
        self._kb = kb
        self._gh = github or GithubSource()
        self._ax = arxiv or ArxivSource()
        self._path = Path(proposals_path) if proposals_path else _PROPOSALS
        self._last: List[dict] = []
        self.stats = {"campaigns": 0, "papers_learned": 0,
                      "repos_learned": 0, "proposals_added": 0,
                      "kb_unavailable": 0}

    # ------------------------------------------------------------ pesquisa
    def run_campaign(self, topic: str = "", source: str = "github") -> dict:
        query = self.CAMPAIGNS.get(_norm(topic), (topic or "").strip())
        if not query:
            query = "football corners prediction analytics"
        res = (self._ax.search(query, 6) if source == "arxiv"
               else self._gh.search_repos(query, 8))
        if not res.get("ok"):
            return res
        with self._lock:
            self._last = list(res.get("findings") or [])
            self.stats["campaigns"] += 1
        tops = "; ".join("%s (%s)" % (f["title"], f["detail"][:40])
                         for f in self._last[:3])
        return {"ok": True, "findings": self._last,
                "speech": ("Pesquisa sobre %s: %d candidatos. Destaques: %s. "
                           "Diga 'proposta numero N' para registrar, ou "
                           "'aprende com o repo/paper' para estudar um."
                           % (query, len(self._last), tops or "nenhum"))}

    # ------------------------------------------------------------ aprender
    def _entry_or(self, ref: str, kind: str) -> Optional[dict]:
        num = _parse_index(ref)
        if num is not None and 1 <= num <= len(self._last) \
                and self._last[num - 1].get("kind") == kind:
            return self._last[num - 1]
        return None

    def learn_repo(self, ref: str) -> dict:
        if self._kb is None:
            self.stats["kb_unavailable"] += 1
            return {"ok": False, "speech": "Base de conhecimento indisponivel."}
        entry = self._entry_or(ref, "repo")
        target = entry["title"] if entry else (ref or "").strip()
        res = self._gh.fetch_readme(target)
        if not res.get("ok"):
            return res
        out = self._kb.add_text("Repo: %s" % res["title"], res["text"],
                                source="https://github.com/%s" % res["title"])
        if out.get("ok"):
            self.stats["repos_learned"] += 1
            out = dict(out)
            out.setdefault("speech", "Repo: %s aprendido no conhecimento." % res["title"])
        return out

    def learn_paper(self, ref: str) -> dict:
        if self._kb is None:
            self.stats["kb_unavailable"] += 1
            return {"ok": False, "speech": "Base de conhecimento indisponivel."}
        entry = self._entry_or(ref, "paper")
        if entry is None:
            res = self._ax.search((ref or "").strip(), 1)
            if not res.get("ok") or not res.get("findings"):
                return {"ok": False,
                        "speech": res.get("speech", "Nada encontrado.")}
            entry = res["findings"][0]
        out = self._kb.add_text("Paper: %s" % entry["title"],
                                entry.get("abstract") or entry.get("detail", ""),
                                source=entry.get("url", ""))
        if out.get("ok"):
            self.stats["papers_learned"] += 1
            out = dict(out)
            out.setdefault("speech", "Paper: %s aprendido no conhecimento." % entry["title"])
        return out

    # ------------------------------------------------------------ propostas
    def _read_all(self) -> List[dict]:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            return [json.loads(l) for l in lines if l.strip()]
        except (OSError, ValueError):
            return []

    def _write_all(self, rows: List[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                 for r in rows) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    def propose(self, index: Any) -> dict:
        num = _parse_index(index)
        if num is None or not (1 <= num <= len(self._last)):
            return {"ok": False,
                    "speech": "Rode uma pesquisa antes e cite o numero do candidato."}
        f = self._last[num - 1]
        rec = {"id": _iso_now(), "kind": f.get("kind"), "title": f.get("title"),
               "url": f.get("url"), "detail": f.get("detail", ""),
               "status": "proposta"}
        with self._lock:
            self._write_all(self._read_all() + [rec])
            self.stats["proposals_added"] += 1
        return {"ok": True,
                "speech": ("Proposta registrada: %s. Implementacao e sua — "
                           "novo chat com o fonte na mesa, Grok instala, "
                           "self-test valida." % f["title"])}

    def list_proposals(self, status: str = "") -> dict:
        rows = self._read_all()
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if not rows:
            return {"ok": True, "speech": "Nenhuma proposta %s."
                    % (status or "registrada")}
        speech = "; ".join("%d. %s (%s)" % (i + 1, r["title"][:60],
                                            r.get("status", "?"))
                           for i, r in enumerate(rows[:6]))
        return {"ok": True, "propostas": rows, "speech": speech}

    def resolve(self, index: Any, status: str = "rejeitada") -> dict:
        num = _parse_index(index)
        rows = self._read_all()
        if num is None or not (1 <= num <= len(rows)):
            return {"ok": False, "speech": "Numero de proposta invalido."}
        status = status if status in ("implementada", "rejeitada") else "rejeitada"
        rows[num - 1]["status"] = status
        with self._lock:
            self._write_all(rows)
        return {"ok": True, "speech": "Proposta '%s' marcada como %s."
                % (rows[num - 1]["title"][:60], status)}

    def stats_dict(self) -> dict:
        with self._lock:
            return {"research_improver": {
                "campaigns": self.stats["campaigns"],
                "papers_learned": self.stats["papers_learned"],
                "repos_learned": self.stats["repos_learned"],
                "proposals_added": self.stats["proposals_added"],
                "proposals_file": str(self._path),
                "github": dict(self._gh.stats),
                "arxiv": dict(self._ax.stats)}}


# ---------------------------------------------------------------------------
# gramatica por voz (encadeada ANTES de web/domestic)
# ---------------------------------------------------------------------------
def parse_research(utterance: str):
    t = _norm(utterance)
    if not t:
        return None
    # resolver ANTES de propor (senao 'marcar proposta 2...' casa em propor)
    m = re.search(r"\b(?:marca|marcar|resolv\w+)\s+(?:a\s+)?proposta\s+"
                  r"(?:numero\s+)?(\d+)\s+(?:como\s+)?"
                  r"(implementad\w+|rejeitad\w+|feita|descartad\w+)", t)
    if m:
        st = "implementada" if m.group(2).startswith("implement") else "rejeitada"
        return ("proposta_resolver", {"indice": m.group(1), "status": st})
    m = re.search(r"\bproposta\s+(?:numero\s+)?(\d+)\b", t)
    if m:
        return ("melhoria_propor", {"indice": m.group(1)})
    if re.search(r"\b(?:quais|liste?|lista)\b.*\bpropostas?\b", t):
        return ("propostas_listar", {})
    if re.search(r"\bpesquis\w+\s+(?:melhorias?|repositorios?|papers?|skills?)",
                 t) or re.match(r"^pesquis\w+\b", t):
        m = re.search(r"\bsobre\s+(.+)$", t)
        return ("pesquisar_melhorias",
                {"topico": m.group(1).strip() if m else ""})
    m = re.search(r"\baprend\w+\s+(?:com\s+)?(?:o|os|a|as)?\s*"
                  r"(?:repo|repositorio)\s+(?:numero\s+)?(.+)$", t)
    if m:
        return ("aprender_repo", {"ref": m.group(1).strip()})
    m = re.search(r"\baprend\w+\s+(?:com\s+)?(?:o|os|a|as)?\s*"
                  r"(?:paper|artigo)\s+(?:numero\s+)?(.+)$", t)
    if m:
        return ("aprender_paper", {"ref": m.group(1).strip()})
    return None


def build_research_tools(cc, ri: ResearchImprover) -> None:
    import inspect
    _csf = "confirm_speech_fn" in inspect.signature(cc.register).parameters

    def t_pesquisar(args, session):
        src = "arxiv" if "arxiv" in _norm(str(args.get("topico", ""))) \
            else "github"
        return ri.run_campaign(str(args.get("topico", "")), source=src)

    cc.register("pesquisar_melhorias",
                "pesquisar repositorios e papers para melhorar o sistema",
                t_pesquisar, "read", args={"topico": "assunto"},
                confirm=False)
    cc.register("aprender_repo",
                "estudar um repositorio (README entra no conhecimento)",
                lambda a, s: ri.learn_repo(str(a.get("ref", ""))),
                "read", args={"ref": "dono/repos ou numero"}, confirm=False)
    cc.register("aprender_paper",
                "estudar um paper arXiv (abstract entra no conhecimento)",
                lambda a, s: ri.learn_paper(str(a.get("ref", ""))),
                "read", args={"ref": "termo, id ou numero"}, confirm=False)
    cc.register("melhoria_propor",
                "registrar um candidato como proposta de melhoria",
                lambda a, s: ri.propose(a.get("indice", "")),
                "read", args={"indice": "numero"}, confirm=False)
    cc.register("propostas_listar", "listar propostas de melhoria",
                lambda a, s: ri.list_proposals(str(a.get("status", ""))),
                "read")
    cc.register("proposta_resolver",
                "marcar proposta como implementada ou rejeitada",
                lambda a, s: ri.resolve(a.get("indice", ""),
                                        str(a.get("status", "rejeitada"))),
                "control", args={"indice": "numero",
                                 "status": "implementada|rejeitada"},
                confirm=False)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    _GH_BODY = json.dumps({"items": [
        {"full_name": "a/toolkit", "html_url": "https://github.com/a/toolkit",
         "stargazers_count": 1200, "language": "Python",
         "description": "Ferramentas de conformal prediction"},
        {"full_name": "b/poisson-live", "html_url": "https://github.com/b/p",
         "stargazers_count": 300, "language": "Python",
         "description": "Poisson in-play"}]}).encode("utf-8")
    _ARXIV = (b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
              b'<entry><title>Conformal Online Calibration</title>'
              b'<summary>We study rolling conformal prediction.</summary>'
              b'<link rel="alternate" href="http://arxiv.org/abs/2401.1"/>'
              b'<published>2024-01-15T00:00:00Z</published></entry></feed>')
    _README = json.dumps({"content": base64.b64encode(
        b"# Toolkit\n\nUtils de conformal prediction em Python.").decode()
    }).encode("utf-8")

    def fake_fetch(url, headers):
        if "search/repositories" in url:
            return 200, {}, _GH_BODY
        if "/readme" in url:
            return 200, {}, _README
        if "arxiv" in url:
            return 200, {}, _ARXIV
        raise OSError("sem rede")

    http = _Http(fetch_fn=fake_fetch)
    gh = GithubSource(http=http, min_interval=999.0, clock=lambda: 1000.0)
    r = gh.search_repos("conformal prediction")
    check("github: 2 findings", r["ok"] is True and len(r["findings"]) == 2)
    check("github: finding com stars", "1200" in r["findings"][0]["detail"])
    r2 = gh.search_repos("outra")
    check("github: rate limit respeitado", r2["ok"] is False
          and "10 buscas" in r2["speech"])
    r3 = gh.fetch_readme("a/toolkit")
    check("github: readme decodifica", r3["ok"] is True
          and "conformal" in r3["text"])
    # O cliente acima foi configurado com throttle extremo para testar o
    # bloqueio. A campanha usa uma instância independente para não herdar
    # esse bloqueio artificial do cenário de teste.
    gh_campaign = GithubSource(http=http, min_interval=0.0,
                               clock=lambda: 1000.0)

    ax = ArxivSource(http=_Http(fetch_fn=fake_fetch), min_interval=0.0,
                     clock=lambda: 1000.0)
    r = ax.search("conformal")
    check("arxiv: entry parseada", r["ok"] is True
          and r["findings"][0]["title"] == "Conformal Online Calibration"
          and "arxiv.org" in r["findings"][0]["url"])

    # gramatica (ordem resolver>proposta!)
    check("gram: pesquisa melhorias",
          parse_research("pesquisa melhorias sobre calibração") ==
          ("pesquisar_melhorias", {"topico": "calibracao"}))
    check("gram: pesquisa geral",
          parse_research("pesquisar repositórios") ==
          ("pesquisar_melhorias", {"topico": ""}))
    check("gram: aprender repo",
          parse_research("aprende com o repo a/toolkit") ==
          ("aprender_repo", {"ref": "a/toolkit"}))
    check("gram: aprender paper por numero",
          parse_research("aprende com o paper numero 2") ==
          ("aprender_paper", {"ref": "2"}))
    check("gram: propor",
          parse_research("proposta numero 1") ==
          ("melhoria_propor", {"indice": "1"}))
    check("gram: resolver NAO colide com propor",
          parse_research("marca a proposta 2 como implementada") ==
          ("proposta_resolver", {"indice": "2", "status": "implementada"}))
    check("gram: listar propostas",
          parse_research("quais propostas temos?") ==
          ("propostas_listar", {}))
    check("gram: conversa comum", parse_research("bom dia") is None)

    with tempfile.TemporaryDirectory(prefix="aura_ri_st_") as td:
        prop = Path(td) / "proposals.jsonl"
        ri = ResearchImprover(github=gh_campaign, arxiv=ax, proposals_path=prop)
        # kb None -> aprender degrada honesto
        r = ri.learn_repo("a/toolkit")
        check("degrade sem kb falado",
              r["ok"] is False and "indisponivel" in r["speech"])

        r = ri.run_campaign("conformal")
        check("campanha: fala candidatos e acao seguinte",
              r["ok"] is True and "candidatos" in r["speech"]
              and "proposta" in r["speech"])
        r = ri.propose("1")
        check("proposta: registrada com protocolo humano",
              r["ok"] is True and "Grok" in r["speech"])
        r = ri.propose("99")
        check("proposta: indice invalido recusado", r["ok"] is False)
        r = ri.list_proposals()
        check("listar: 1 proposta 'proposta'",
              r["ok"] is True and "a/toolkit" in r["speech"])
        r = ri.resolve("1", "implementada")
        check("resolver: status atualizado",
              r["ok"] is True and ri.list_proposals("implementada")["ok"])

        # campanha arxiv + learn por indice (precisa de kb)
        try:
            from web_knowledge import ToolKnowledge
        except Exception:
            ToolKnowledge = None  # type: ignore
        if ToolKnowledge is None:
            print("[SKIP] web_knowledge nao importavel aqui")
        else:
            kb = ToolKnowledge(kb_dir=Path(td) / "kb")
            ri2 = ResearchImprover(kb=kb, github=gh_campaign, arxiv=ax,
                                   proposals_path=prop)
            ri2.run_campaign("conformal", source="arxiv")
            r = ri2.learn_paper("1")
            check("paper: aprendido no conhecimento",
                  r["ok"] is True and "Paper:" in r.get("speech", ""))
            r = ri2.learn_repo("a/toolkit")
            check("repo: README aprendido",
                  r["ok"] is True and "Repo:" in r.get("speech", ""))
            hits = kb.query("rolling conformal prediction")
            check("kb: pesquisa academica consultavel",
                  hits and "conformal" in hits[0]["text"].lower())

        st = ri.stats_dict()["research_improver"]
        check("stats: campanhas e propostas contadas",
              st["campaigns"] >= 1 and st["proposals_added"] == 1)

    # integracao CommandCenter
    try:
        from jarvis_command_center import CommandCenter
    except Exception:
        CommandCenter = None  # type: ignore
    if CommandCenter is None:
        print("[SKIP] jarvis_command_center nao importavel aqui")
    else:
        with tempfile.TemporaryDirectory(prefix="aura_ri_cc_") as td:
            ri3 = ResearchImprover(
                github=GithubSource(http=_Http(fetch_fn=fake_fetch),
                                    min_interval=0.0, clock=time.monotonic),
                arxiv=ax, proposals_path=Path(td) / "p.jsonl")
            cc = CommandCenter()
            build_research_tools(cc, ri3)
            r = cc.execute("pesquisar_melhorias", {"topico": "conformal"}, "u")
            check("cc: pesquisa fala candidatos",
                  r["ok"] is True and "candidatos" in r["speech"])
            r = cc.execute("melhoria_propor", {"indice": "1"}, "u")
            check("cc: proposta sem confirmacao extra (bookkeeping)",
                  r["ok"] is True and "Grok" in r["speech"])

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - research_improver.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
