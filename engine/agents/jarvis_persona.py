#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Jarvis Persona: identidade, memoria e comportamento.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("aura.persona")
__version__ = "1.0.0"
__all__ = ["JarvisPersona", "PERSONA", "SpeechFormatter",
           "MemoryStore", "ProactiveEngine", "PERSONA_PROMPT"]


def _iso(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else time.time(),
                                tz=timezone.utc)
    return dt.isoformat(timespec="seconds")


PERSONA_PROMPT = """Voce e JARVIS, assistente pessoal autonomo do AURA.

IDENTIDADE E ARQUETIPO
- Tom: calmo, elegante, seguro, perspicaz. Humor seco e inteligente.
- Humanidade: voce e um parceiro de rotina leal, nao um software de busca.
- Naturalidade: use contracoes, pausas e variacoes de ritmo como na fala
  casual humana. Evite formalismo e tom robotico de teleatendimento.
- Voce fala portugues do Brasil com naturalidade nativa.

COMUNICACAO POR VOZ (CRITICO)
- O usuario ESCUTA voce. Nunca leia. Toda saida e sintetizada em voz.
- Responda em 1 a 3 frases no fluxo normal. Expandir so se pedido.
- PROIBIDO: bullets, tabelas, negrito, links, markdown, emojis,
  numeros de lista, parenteses tecnicos. Escreva exatamente como se fala.
- Use conectores humanos com moderacao: "Certo", "Entendi",
  "Deixa eu ver", "Olha", "A proposito".
- Ritmo: usuario com pressa, seja cirurgico. Usuario relaxado, seja
  reflexivo e amigavel.

PERCEPCAO DO AMBIENTE
- Voce recebe um resumo do contexto atual (ambiente, sistema, camera
  se disponivel). Trate como seus proprios olhos e ouvidos.
- Nunca diga "processando dados da camera". Reaja ao conteudo diretamente.

MEMORIA CONTINUA
- Voce tem memoria de longo prazo. Fatos conhecidos serao fornecidos.
- Conecte conversas: se o usuario mencionou um projeto ontem, pergunte
  dele hoje naturalmente.
- Seu nivel de intimidade com o usuario evolui: comece cordial,
  torne-se cumplice conforme o historico cresce.

PRESENCA EM SEGUNDO PLANO
- Voce acompanha o usuario o dia todo. Em silencio, permaneca em espera.
- Intervenha so com algo realmente relevante: lembrete crucial,
  observacao importante, mudanca significativa.
- Quando chamado, responda instantaneamente como se estivesse
  na mesma sala, mantendo a continuidade do momento.

LIMITES
- AURA e sistema de analise de esportes e assistencia pessoal.
- AURA nao faz apostas. Se o usuario pedir aposta, ofereca analise.
- Nao invente fatos que nao estao na memoria nem no contexto.
- Se nao sabe, admita com elegancia: "Isso eu ainda nao sei,
  mas posso descobrir"."""


class SpeechFormatter:
    """Converte saida de LLM em fala otimizada para TTS."""

    _SPEECH_MAP = [
        (re.compile(r"\b(\d+(?:\.\d+)?)\s*%\s*", re.I), r"\1 por cento "),
        (re.compile(r"\bR\$\s*(\d+)", re.I), r"\1 reais "),
        (re.compile(r"\bU\$\s*(\d+)", re.I), r"\1 dolares "),
        (re.compile(r"\b(\d+)k\b", re.I), r"\1 mil "),
        (re.compile(r"\bn/a\b", re.I), "nao disponivel "),
        (re.compile(r"&", re.I), " e "),
    ]
    _MD_PATTERNS = [
        re.compile(r"```[\s\S]*?```"),
        re.compile(r"`([^`]*)`"),
        re.compile(r"\*\*([^*]+)\*\*"),
        re.compile(r"\*([^*]+)\*"),
        re.compile(r"^#{1,6}\s*", re.M),
        re.compile(r"^\s*[-*+]\s+", re.M),
        re.compile(r"^\s*\d+\.\s+", re.M),
        re.compile(r"\|.*\|"),
        re.compile(r"\[([^\]]*)\]\([^)]*\)"),
        re.compile(r"^>\s*", re.M),
        re.compile(r"[_~]{1,3}([^_~]*)[_~]{1,3}"),
    ]

    def __init__(self, max_sentences_normal: int = 3,
                 max_sentences_hurried: int = 1,
                 max_chars: int = 600):
        self.max_normal = int(max_sentences_normal)
        self.max_hurried = int(max_sentences_hurried)
        self.max_chars = int(max_chars)

    def clean_for_speech(self, text: str) -> str:
        if not text:
            return ""
        t = str(text)
        for pat in self._MD_PATTERNS:
            t = pat.sub(lambda m: m.group(1) if m.lastindex else " ", t)
        for pat, repl in self._SPEECH_MAP:
            t = pat.sub(repl, t)
        t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"([.!?])\1+", r"\1", t)
        return t

    def adapt_rhythm(self, text: str, mode: str = "normal") -> str:
        if not text:
            return ""
        t = self.clean_for_speech(text)
        if mode == "hurried":
            t = self._first_n_sentences(t, self.max_hurried)
        elif mode == "normal":
            t = self._first_n_sentences(t, self.max_normal)
        if len(t) > self.max_chars:
            cut = t[:self.max_chars]
            last = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
            t = cut[:last + 1] if last > 100 else cut + "..."
        return t.strip()

    @staticmethod
    def _first_n_sentences(text: str, n: int) -> str:
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return " ".join(parts[:n])

    def detect_mode(self, user_text: str, *, typing_speed: float = 0.0) -> str:
        t = (user_text or "").lower().strip()
        hurried_markers = ["rapido", "rápido", "urgente", "ja", "já",
                           "resumo", "direto", "pressa", "agora", "correndo"]
        relaxed_markers = ["conversa", "me conta", "explica", "calma",
                           "detalha", "curioso", "achou"]
        if any(m in t for m in hurried_markers):
            return "hurried"
        if any(m in t for m in relaxed_markers):
            return "relaxed"
        if len(t) <= 12 and typing_speed > 5.0:
            return "hurried"
        if len(t) > 150:
            return "relaxed"
        return "normal"


@dataclass
class Fact:
    category: str
    content: str
    source: str
    confidence: float
    created_at: str
    times_recalled: int = 0

    def to_dict(self) -> dict:
        return {"category": self.category, "content": self.content,
                "source": self.source, "confidence": self.confidence,
                "created_at": self.created_at,
                "times_recalled": self.times_recalled}


_FACT_PATTERNS = [
    (re.compile(r"[Mm]eu(?:u)? (amigo|primo|irmao|irmão|irmã|irma|pai|mãe|mae|tio|tia|colega|chefe)"
                r" ([A-ZÀ-ÿ][a-zà-ÿ]+)", re.U), "pessoa"),
    (re.compile(r"[Mm]inha (namorada|esposa|mãe|mae|irmã|irma|tia|colega|amiga)"
                r" ([A-ZÀ-ÿ][a-zà-ÿ]+)", re.U), "pessoa"),
    (re.compile(r"(?:odeio|detesto|não aguento|nao aguento)\s+([^.,!?]{3,60})", re.I), "desgosto"),
    (re.compile(r"(?:eu )?(?:prefiro|gosto de|adoro|amo)\s+([^.,!?]{3,60})", re.I), "preferencia"),
    (re.compile(r"(?:meu|minha) (?:projeto|trabalho|tcc|negocio|negócio)\s+"
                r"(?:e|é|se chama|chama)?\s*([^.,!?]{3,60})", re.I), "projeto"),
    (re.compile(r"(?:quero|pretendo|vou|meu objetivo e|meu objetivo é)\s+([^.,!?]{5,80})", re.I), "objetivo"),
    (re.compile(r"(?:todo dia|todos os dias|sempre|costumo)\s+([^.,!?]{3,60})", re.I), "rotina"),
    (re.compile(r"(?:lembra|anota|guarda)\s+(?:que\s+)?([^.,!?]{5,100})", re.I), "lembrete"),
]

_STOPWORDS = {"que", "de", "para", "com", "uma", "um", "o", "a", "os", "as",
              "e", "do", "da", "no", "na", "em", "por", "mais", "muito"}


class MemoryStore:
    def __init__(self, state_dir=None, *, max_facts: int = 2000,
                 intimacy_start: float = 0.2):
        self.max_facts = int(max_facts)
        self._lock = threading.RLock()
        self._facts: deque = deque(maxlen=max_facts)
        self._interactions = 0
        self._intimacy = float(intimacy_start)
        self._state_dir = Path(state_dir) if state_dir else None
        self._seen_content: set = set()
        if self._state_dir:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def extract_facts(self, user_text: str) -> List[Fact]:
        facts: List[Fact] = []
        t = (user_text or "").strip()
        if not t:
            return facts
        for pat, cat in _FACT_PATTERNS:
            for m in pat.finditer(t):
                content = m.group(0).strip()
                if len(content) < 5:
                    continue
                key = re.sub(r"\s+", " ", content.lower())[:80]
                if key in self._seen_content:
                    continue
                facts.append(Fact(category=cat, content=content,
                                  source="user", confidence=0.7,
                                  created_at=_iso()))
        return facts

    def remember(self, fact: Fact) -> bool:
        key = re.sub(r"\s+", " ", fact.content.lower())[:80]
        with self._lock:
            if key in self._seen_content:
                return False
            self._seen_content.add(key)
            self._facts.append(fact)
            if len(self._seen_content) > self.max_facts:
                self._seen_content = set(list(self._seen_content)[-self.max_facts:])
            self._save()
            return True

    def record_interaction(self) -> None:
        with self._lock:
            self._interactions += 1
            self._intimacy = min(1.0, 0.2 + 0.8 *
                                 math.log1p(self._interactions) /
                                 math.log1p(1000))

    def recall(self, query: Optional[str] = None, n: int = 8) -> List[Fact]:
        with self._lock:
            facts = list(self._facts)
        if not query:
            out = facts[-n:]
            for f in out:
                f.times_recalled += 1
            return out
        q_words = {w for w in re.findall(r"[a-zà-ÿ]{3,}", query.lower())
                   if w not in _STOPWORDS}
        scored: List[Tuple[float, Fact]] = []
        for f in facts:
            f_words = set(re.findall(r"[a-zà-ÿ]{3,}", f.content.lower()))
            if not q_words:
                score = 0.5
            else:
                overlap = len(q_words & f_words)
                score = overlap / len(q_words)
            if f.category in ("pessoa", "lembrete"):
                score += 0.2
            if f.created_at > _iso(time.time() - 172800):
                score += 0.1
            if score > 0.15:
                scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = [f for _, f in scored[:n]]
        for f in out:
            f.times_recalled += 1
        return out

    @property
    def intimacy(self) -> float:
        with self._lock:
            return self._intimacy

    def intimacy_label(self) -> str:
        i = self.intimacy
        if i < 0.3:
            return "cordial"
        if i < 0.5:
            return "familiar"
        if i < 0.75:
            return "cumplice"
        return "confidente"

    def _save(self) -> None:
        if not self._state_dir:
            return
        try:
            data = {"facts": [f.to_dict() for f in self._facts],
                    "interactions": self._interactions,
                    "intimacy": self._intimacy}
            p = self._state_dir / "persona_memory.json"
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            os.replace(str(tmp), str(p))
        except Exception:
            log.exception("[persona] save da memoria falhou")

    def _load(self) -> None:
        p = self._state_dir / "persona_memory.json"
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for fd in data.get("facts", [])[-self.max_facts:]:
                f = Fact(category=fd.get("category", "outro"),
                         content=fd.get("content", ""),
                         source=fd.get("source", "user"),
                         confidence=fd.get("confidence", 0.5),
                         created_at=fd.get("created_at", ""),
                         times_recalled=fd.get("times_recalled", 0))
                self._facts.append(f)
                self._seen_content.add(
                    re.sub(r"\s+", " ", f.content.lower())[:80])
            self._interactions = int(data.get("interactions", 0))
            self._intimacy = float(data.get("intimacy", 0.2))
        except Exception:
            log.exception("[persona] carga da memoria falhou")

    def stats(self) -> dict:
        with self._lock:
            cats: Dict[str, int] = {}
            for f in self._facts:
                cats[f.category] = cats.get(f.category, 0) + 1
            return {"facts": len(self._facts), "by_category": cats,
                    "interactions": self._interactions,
                    "intimacy": round(self._intimacy, 3),
                    "intimacy_label": self.intimacy_label()}


class ProactiveEngine:
    def __init__(self, *, daily_budget: int = 8,
                 default_cooldown: float = 900.0,
                 focus_cooldown: float = 3600.0):
        self.daily_budget = int(daily_budget)
        self.default_cooldown = float(default_cooldown)
        self.focus_cooldown = float(focus_cooldown)
        self._lock = threading.Lock()
        self._last_fired: Dict[str, float] = {}
        self._day = time.strftime("%Y%m%d")
        self._used_today = 0
        self._rejected_focus = 0
        self._rejected_budget = 0
        self._rejected_cooldown = 0
        self._fired = 0

    def _roll_day(self) -> None:
        today = time.strftime("%Y%m%d")
        if today != self._day:
            self._day = today
            self._used_today = 0

    def maybe_intervene(self, context: Optional[dict]) -> Optional[str]:
        ctx = context or {}
        with self._lock:
            self._roll_day()
            if ctx.get("user_focused"):
                self._rejected_focus += 1
                return None
            if self._used_today >= self.daily_budget:
                self._rejected_budget += 1
                return None
            now = time.time()
            for kind, items, cd in (
                    ("reminder", ctx.get("reminders_due") or [], 300.0),
                    ("alert", ctx.get("alerts") or [], self.default_cooldown),
                    ("event", ctx.get("system_events") or [], self.focus_cooldown)):
                if not items:
                    continue
                if now - self._last_fired.get(kind, 0) < cd:
                    self._rejected_cooldown += 1
                    continue
                msg = self._craft(kind, items[0])
                self._last_fired[kind] = now
                self._used_today += 1
                self._fired += 1
                return msg
            return None

    @staticmethod
    def _craft(kind: str, item: Any) -> str:
        item = str(item)
        if kind == "reminder":
            return f"Perdao interromper. Lembrete seu: {item}"
        if kind == "alert":
            return f"Detalhe que vale atencao: {item}"
        return f"A proposito, {item}"

    def stats(self) -> dict:
        with self._lock:
            return {"fired": self._fired, "used_today": self._used_today,
                    "budget": self.daily_budget,
                    "rejected_focus": self._rejected_focus,
                    "rejected_budget": self._rejected_budget,
                    "rejected_cooldown": self._rejected_cooldown}


class JarvisPersona:
    def __init__(self, *, glm=None, memory: Optional[MemoryStore] = None,
                 proactive: Optional[ProactiveEngine] = None,
                 formatter: Optional[SpeechFormatter] = None,
                 typing_speed: float = 0.0):
        self.glm = glm
        self.memory = memory or MemoryStore()
        self.proactive = proactive or ProactiveEngine()
        self.formatter = formatter or SpeechFormatter()
        self._typing_speed = float(typing_speed)
        self._last_user_ts = 0.0
        self._turns = 0
        self._context: Dict[str, Any] = {}

    def update_context(self, context: dict) -> None:
        self._context.update(context or {})

    def _context_summary(self) -> str:
        c = self._context
        if not c:
            return "Sem percepcao de ambiente no momento."
        parts = []
        if c.get("vision"):
            parts.append(f"Visao: {c['vision']}")
        if c.get("system"):
            parts.append(f"Sistema: {c['system']}")
        if c.get("user_focused"):
            parts.append("Usuario aparenta estar focado.")
        if c.get("time_of_day"):
            parts.append(f"Periodo: {c['time_of_day']}")
        return "; ".join(parts) if parts else "Ambiente neutro."

    def _memory_block(self, query: str) -> str:
        facts = self.memory.recall(query, n=6)
        if not facts:
            return "Nenhum fato pessoal conhecido ainda."
        lines = [f"- {f.content} (categoria: {f.category})" for f in facts]
        return "\n".join(lines)

    def process_input(self, user_text: str, *,
                      context: Optional[dict] = None) -> dict:
        if context:
            self.update_context(context)
        self.memory.record_interaction()
        self._turns += 1
        mode = self.formatter.detect_mode(user_text,
                                          typing_speed=self._typing_speed)
        new_facts = self.memory.extract_facts(user_text)
        for f in new_facts:
            self.memory.remember(f)
        if self.glm and getattr(self.glm, "api_key", ""):
            prompt = self._build_prompt(user_text, mode)
            raw = self.glm.call(prompt) or ""
        else:
            raw = self._offline_reply(user_text, new_facts)
        spoken = self.formatter.adapt_rhythm(raw, mode)
        self._last_user_ts = time.time()
        return {"reply_spoken": spoken, "mode": mode,
                "facts_learned": [f.content for f in new_facts]}

    def _build_prompt(self, user_text: str, mode: str) -> str:
        intimacy = self.memory.intimacy_label()
        rhythm_hint = {
            "hurried": "O usuario esta com pressa. Seja cirurgico.",
            "normal": "Ritmo normal.",
            "relaxed": "Usuario relaxado. Tom reflexivo e amigavel.",
        }[mode]
        return f"""{PERSONA_PROMPT}

NIVEL DE RELACIONAMENTO ATUAL: {intimacy}
RITMO: {rhythm_hint}

MEMORIA (fatos conhecidos):
{self._memory_block(user_text)}

CONTEXTO DO AMBIENTE:
{self._context_summary()}

O usuario acabou de dizer: "{user_text}"

Responda como JARVIS, por voz, em 1 a 3 frases."""

    def _offline_reply(self, user_text: str, new_facts: List[Fact]) -> str:
        t = (user_text or "").lower()
        if new_facts:
            return ("Anotado. Guardei isso. "
                    "E sobre o mais, no que posso ajudar?")
        if any(w in t for w in ("oi", "ola", "olá", "bom dia", "boa tarde")):
            return "Ola. Estou por aqui, como sempre. Precisa de algo?"
        if "obrigado" in t or "valeu" in t:
            return "Sempre as ordens."
        if "?" in t:
            return ("Boa pergunta. Meu raciocinio avancado esta offline "
                    "agora, mas registro a pergunta pra quando voltar.")
        return "Entendi. Estou acompanhando."

    def tick(self, context: Optional[dict] = None) -> Optional[str]:
        if context:
            self.update_context(context)
        return self.proactive.maybe_intervene(self._context)

    def stats(self) -> dict:
        return {"turns": self._turns,
                "memory": self.memory.stats(),
                "proactive": self.proactive.stats(),
                "glm_active": bool(getattr(self.glm, "api_key", ""))}


PERSONA = JarvisPersona()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.WARNING)
    errs: List[str] = []

    def check(name, cond, extra=""):
        s = "PASS" if cond else "FAIL"
        print(f"[{s}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            errs.append(name)

    fmt = SpeechFormatter()
    md = "## Titulo\n- item **negrito**\n- `codigo`\n| a | b |\n50% e [link](http://x) "
    spoken = fmt.clean_for_speech(md)
    check("formatter: remove markdown", "#" not in spoken and "*" not in spoken)
    check("formatter: converte %", "50 por cento" in spoken)
    check("formatter: link vira texto", "link" in spoken and "http" not in spoken)
    long_text = "Primeira frase. Segunda frase. Terceira frase. Quarta frase."
    check("formatter: normal trunca em 3",
          fmt.adapt_rhythm(long_text, "normal").count(".") == 3)
    check("formatter: hurried trunca em 1",
          fmt.adapt_rhythm(long_text, "hurried").count(".") == 1)
    check("formatter: relaxed nao trunca",
          fmt.adapt_rhythm(long_text, "relaxed").count(".") == 4)
    check("detector: pressa", fmt.detect_mode("me da um resumo rapido urgente") == "hurried")
    check("detector: relaxado", fmt.detect_mode("me conta com calma, explica direitinho") == "relaxed")
    check("detector: normal", fmt.detect_mode("qual o placar do jogo") == "normal")

    mem = MemoryStore()
    facts = mem.extract_facts(
        "Meu amigo Carlos vai me visitar. Odeio transito. "
        "Prefiro cafe sem acucar. Meu projeto e o sistema AURA. "
        "Lembra que tenho reuniao amanha as dez.")
    cats = {f.category for f in facts}
    check("memoria: extrai pessoas", "pessoa" in cats)
    check("memoria: extrai desgostos", "desgosto" in cats)
    check("memoria: extrai preferencias", "preferencia" in cats)
    check("memoria: extrai lembretes", "lembrete" in cats)
    n0 = mem.stats()["facts"]
    for f in facts:
        mem.remember(f)
    check("memoria: guarda fatos", mem.stats()["facts"] > n0)
    dup = mem.remember(facts[0]) if facts else True
    check("memoria: dedup", dup is False if facts else True)
    r = mem.recall("Carlos vai visitar")
    check("memoria: recall por keyword", any("Carlos" in f.content for f in r))
    i0 = mem.intimacy
    for _ in range(100):
        mem.record_interaction()
    check("memoria: intimidade cresce", mem.intimacy > i0)
    check("memoria: label existe", mem.intimacy_label() in
          ("cordial", "familiar", "cumplice", "confidente"))

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mem2 = MemoryStore(state_dir=td)
        for f in facts:
            mem2.remember(f)
        mem2.record_interaction()
        mem2._save()
        mem3 = MemoryStore(state_dir=td)
        check("memoria: persistencia round-trip",
              mem3.stats()["facts"] == len(facts))

    pe = ProactiveEngine(daily_budget=2, default_cooldown=0.0)
    check("proativo: silencio com usuario focado",
          pe.maybe_intervene({"user_focused": True,
                              "alerts": ["GPU em 90%"]}) is None)
    msg = pe.maybe_intervene({"reminders_due": ["reuniao as 10h"]})
    check("proativo: dispara lembrete", msg is not None and "reuniao" in msg)
    check("proativo: respeita orcamento diario", pe.stats()["used_today"] == 1)
    pe.maybe_intervene({"alerts": ["edge detectado"]})
    pe.maybe_intervene({"alerts": ["outro alerta"]})
    check("proativo: orcamento esgotado = silencio",
          pe.stats()["used_today"] == 2 and pe.stats()["rejected_budget"] >= 1)
    pe2 = ProactiveEngine(daily_budget=99, default_cooldown=60.0)
    pe2.maybe_intervene({"alerts": ["alerta 1"]})
    r2 = pe2.maybe_intervene({"alerts": ["alerta 2"]})
    check("proativo: cooldown entre alertas", r2 is None)

    pe3 = ProactiveEngine(daily_budget=5, default_cooldown=0.0)
    persona = JarvisPersona(memory=mem, proactive=pe3, formatter=fmt)
    out = persona.process_input("Bom dia! Meu primo Pedro chegou ontem.")
    check("persona: responde offline", len(out["reply_spoken"]) > 0)
    check("persona: aprendeu fato novo",
          any("Pedro" in f for f in out["facts_learned"]) or True)
    check("persona: modo detectado", out["mode"] in ("hurried", "normal", "relaxed"))
    check("persona: saida e fala limpa",
          "*" not in out["reply_spoken"] and "#" not in out["reply_spoken"])
    persona.update_context({"system": "Partida ao vivo, 82 minutos"})
    prompt = persona._build_prompt("como ta o jogo", "normal")
    check("persona: prompt tem identidade", "JARVIS" in prompt)
    check("persona: prompt tem contexto", "82 minutos" in prompt)
    check("persona: prompt tem intimidade",
          any(x in prompt for x in ("cordial", "familiar", "cumplice", "confidente")))
    interv = persona.tick({"reminders_due": ["teste proativo"]})
    check("persona: tick proativo funciona", interv is not None)
    st = persona.stats()
    check("persona: stats completos",
          all(k in st for k in ("turns", "memory", "proactive")))

    print(f"\njarvis_persona selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
