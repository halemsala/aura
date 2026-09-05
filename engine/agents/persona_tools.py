#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Persona Tools: function calling de memoria viva.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.persona_tools")
__version__ = "1.0.0"
__all__ = ["TOOL_SCHEMAS", "PersonaToolRouter", "ContextProviders",
           "importance_of", "TOOLS", "call_glm_with_tools"]

try:
    from engine.agents.jarvis_persona import MemoryStore, Fact
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.agents.jarvis_persona import MemoryStore, Fact


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "save_user_memory",
            "description": "Armazena fato/preferencia sobre o usuario na memoria local.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["preferencia", "rotina", "pessoa_relevante",
                                 "projeto", "saude_bem_estar", "lembrete",
                                 "desgosto", "objetivo", "fato_geral"],
                    },
                    "fact": {"type": "string"},
                    "importance": {"type": "integer"},
                },
                "required": ["category", "fact", "importance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_user_memory",
            "description": "Busca fatos relevantes da memoria por topico.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_context",
            "description": "Retorna contexto ambiental atual.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_CAT_MAP = {
    "preferencia": "preferencia", "rotina": "rotina",
    "pessoa_relevante": "pessoa", "projeto": "projeto",
    "saude_bem_estar": "saude", "lembrete": "lembrete",
    "desgosto": "desgosto", "objetivo": "objetivo",
    "fato_geral": "outro",
}
_IMPORTANCE_BASE = {
    "saude": 5, "pessoa": 4, "lembrete": 4, "projeto": 3,
    "preferencia": 2, "rotina": 2, "desgosto": 2, "objetivo": 3,
    "outro": 1,
}
_URGENCY_WORDS = ("urgente", "critico", "crítico", "medico", "médico",
                  "hospital", "cirurgia", "aniversario", "aniversário",
                  "entrevista", "prova", "viagem")


def importance_of(category: str, content: str) -> int:
    cat = _CAT_MAP.get(str(category or "").lower(), "outro")
    base = _IMPORTANCE_BASE.get(cat, 1)
    c = (content or "").lower()
    if any(w in c for w in _URGENCY_WORDS):
        base = min(5, base + 1)
    if re.search(r"\b\d{1,2}[:h]\d{2}\b|\b\d{1,2}h\b", c):
        base = min(5, base + 1)
    return max(1, min(5, base))


class PersonaToolRouter:
    def __init__(self, memory: MemoryStore):
        self.memory = memory
        self._importance: Dict[str, int] = {}
        self._lock = threading.Lock()
        self.calls_save = 0
        self.calls_retrieve = 0
        self.calls_context = 0
        self.errors = 0

    def _key(self, content: str) -> str:
        return re.sub(r"\s+", " ", (content or "").lower())[:80]

    def save_user_memory(self, category: str, fact: str,
                         importance: Optional[int] = None) -> str:
        try:
            cat = _CAT_MAP.get(str(category or "").lower(), "outro")
            content = str(fact or "").strip()
            if len(content) < 3:
                return json.dumps({"status": "error", "message": "fato vazio"},
                                  ensure_ascii=False)
            imp = importance_of(category, content)
            if isinstance(importance, int) and 1 <= importance <= 5:
                imp = max(imp - 1, min(importance, imp + 1))
            f = Fact(category=cat, content=content, source="user",
                     confidence=0.8, created_at=_iso())
            created = self.memory.remember(f)
            with self._lock:
                self._importance[self._key(content)] = imp
            self.calls_save += 1
            return json.dumps({"status": "success", "created": created,
                               "importance": imp, "category": cat},
                              ensure_ascii=False)
        except Exception as e:
            self.errors += 1
            return json.dumps({"status": "error", "message": str(e)},
                              ensure_ascii=False)

    def retrieve_user_memory(self, query: str, n: int = 5) -> str:
        try:
            facts = self.memory.recall(query, n=max(n * 4, 16))
            with self._lock:
                scored = [(self._importance.get(self._key(f.content), 1), f)
                          for f in facts]
            scored.sort(key=lambda x: x[0], reverse=True)
            out = [{"category": f.category, "fact": f.content,
                    "importance": imp} for imp, f in scored[:n]]
            self.calls_retrieve += 1
            return json.dumps({"retrieved_memories": out}, ensure_ascii=False)
        except Exception as e:
            self.errors += 1
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def handle(self, name: str, args: Optional[dict]) -> str:
        args = args or {}
        if name == "save_user_memory":
            return self.save_user_memory(args.get("category", "fato_geral"),
                                         args.get("fact", ""),
                                         args.get("importance"))
        if name == "retrieve_user_memory":
            return self.retrieve_user_memory(args.get("query", ""))
        if name == "get_current_context":
            self.calls_context += 1
            return json.dumps({"info": "use ContextProviders.snapshot()"},
                              ensure_ascii=False)
        return json.dumps({"error": f"funcao desconhecida: {name}"},
                          ensure_ascii=False)

    def stats(self) -> dict:
        with self._lock:
            return {"calls_save": self.calls_save,
                    "calls_retrieve": self.calls_retrieve,
                    "calls_context": self.calls_context,
                    "errors": self.errors,
                    "importance_index": len(self._importance)}


class ContextProviders:
    def __init__(self, *, extra: Optional[Dict[str, Callable[[], Any]]] = None):
        self._extra = dict(extra or {})
        self._psutil = None
        try:
            import psutil  # type: ignore
            self._psutil = psutil
        except ImportError:
            pass

    def register(self, name: str, fn: Callable[[], Any]) -> None:
        self._extra[str(name)] = fn

    @staticmethod
    def _period(hour: int) -> str:
        if 5 <= hour < 12:
            return "manha"
        if 12 <= hour < 18:
            return "tarde"
        if 18 <= hour < 23:
            return "noite"
        return "madrugada"

    def snapshot(self) -> dict:
        now = datetime.now()
        ctx: Dict[str, Any] = {
            "time_of_day": self._period(now.hour),
            "clock": now.strftime("%H:%M"),
            "weekday": ["segunda", "terca", "quarta", "quinta",
                        "sexta", "sabado", "domingo"][now.weekday()],
        }
        if self._psutil is not None:
            try:
                b = self._psutil.sensors_battery()
                if b:
                    ctx["battery_pct"] = round(b.percent)
                    ctx["plugged"] = bool(b.power_plugged)
            except Exception:
                pass
        for name, fn in self._extra.items():
            try:
                v = fn()
                if v is not None:
                    ctx[name] = v
            except Exception:
                log.debug("[ctx] provider %s falhou", name)
        return ctx

    def summary_for_prompt(self) -> str:
        c = self.snapshot()
        parts = [f"{c['weekday']} de {c['time_of_day']}, {c['clock']}"]
        if "battery_pct" in c:
            plug = " (carregando)" if c.get("plugged") else ""
            parts.append(f"bateria {c['battery_pct']}%{plug}")
        for k in ("game", "system", "alerts"):
            if k in c and c[k]:
                parts.append(f"{k}: {c[k]}")
        return "; ".join(parts)


def call_glm_with_tools(glm: Any, user_text: str, router: PersonaToolRouter,
                        *, max_rounds: int = 2) -> Optional[str]:
    if not glm or not getattr(glm, "api_key", ""):
        return None
    messages: List[dict] = [{"role": "user", "content": user_text}]
    for _ in range(max_rounds):
        try:
            payload = {"model": glm.model, "messages": messages,
                       "tools": TOOL_SCHEMAS, "tool_choice": "auto",
                       "max_tokens": glm.max_tokens}
            import urllib.request
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                glm.api_url, data=data,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {glm.api_key}"})
            with urllib.request.urlopen(req, timeout=glm.timeout) as r:
                resp = json.loads(r.read())
            msg = (resp.get("choices", [{}])[0].get("message") or {})
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return msg.get("content") or ""
            messages.append(msg)
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = router.handle(fn.get("name", ""), args)
                messages.append({"role": "tool",
                                 "tool_call_id": tc.get("id", ""),
                                 "content": result})
        except Exception as e:
            log.error("[persona_tools] GLM tools falhou: %s", e)
            return None
    return None


TOOLS = PersonaToolRouter


if __name__ == "__main__":
    import sys
    import tempfile
    logging.basicConfig(level=logging.WARNING)
    errs: List[str] = []

    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c:
            errs.append(n)

    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    check("schemas: 3 tools", names == {"save_user_memory",
                                        "retrieve_user_memory",
                                        "get_current_context"})
    for t in TOOL_SCHEMAS:
        fn = t["function"]
        check(f"schema {fn['name']}: tem parametros",
              "parameters" in fn and "description" in fn)

    check("importance: saude=5",
          importance_of("saude_bem_estar", "dor no joelho") == 5)
    check("importance: pessoa=4",
          importance_of("pessoa_relevante", "meu primo Pedro") == 4)
    check("importance: urgencia sobe",
          importance_of("fato_geral", "reuniao urgente amanha") >= 2)
    check("importance: horario sobe lembrete",
          importance_of("lembrete", "medico as 14h") == 5)
    check("importance: clamp 1-5", importance_of("fato_geral", "x") == 1)

    mem = MemoryStore()
    router = PersonaToolRouter(mem)
    r1 = json.loads(router.save_user_memory(
        "pessoa_relevante", "Meu primo Pedro chega sexta", 4))
    check("router: save success",
          r1["status"] == "success" and r1["importance"] == 4)
    r2 = json.loads(router.save_user_memory(
        "preferencia", "Prefiro cafe sem acucar"))
    check("router: save sem importance", r2["importance"] == 2)
    r3 = json.loads(router.save_user_memory(
        "pessoa_relevante", "Meu primo Pedro chega sexta"))
    check("router: dedup", r3["status"] == "success" and r3["created"] is False)
    router.save_user_memory("fato_geral", "Gosta de futebol aos domingos", 1)
    got = json.loads(router.retrieve_user_memory("Pedro chega quando?"))
    mems = got.get("retrieved_memories", [])
    check("router: retrieve acha fato", any("Pedro" in m["fact"] for m in mems))
    check("router: retrieve traz importance",
          all("importance" in m for m in mems))

    router.save_user_memory("saude_bem_estar", "Alergia a frutos do mar", 5)
    router.save_user_memory("fato_geral", "Gosta de cachorro", 1)
    got2 = json.loads(router.retrieve_user_memory("alergia mar cachorro Pedro"))
    imps = [m["importance"] for m in got2.get("retrieved_memories", [])]
    check("router: ordenacao por importance",
          imps == sorted(imps, reverse=True), f"{imps}")

    bad = json.loads(router.handle("nao_existe", {}))
    check("router: funcao desconhecida", "error" in bad)

    with tempfile.TemporaryDirectory() as td:
        mem2 = MemoryStore(state_dir=td)
        rt2 = PersonaToolRouter(mem2)
        rt2.save_user_memory("projeto", "AURA e o projeto principal", 3)
        mem2._save()
        mem3 = MemoryStore(state_dir=td)
        got3 = json.loads(PersonaToolRouter(mem3).retrieve_user_memory("projeto AURA"))
        check("persistencia: fato sobrevive",
              any("AURA" in m["fact"] for m in got3.get("retrieved_memories", [])))

    cp = ContextProviders(extra={"game": lambda: "82 min, 1x0"})
    snap = cp.snapshot()
    check("ctx: hora e periodo", "clock" in snap and "time_of_day" in snap)
    check("ctx: callback extra", snap.get("game") == "82 min, 1x0")
    summ = cp.summary_for_prompt()
    check("ctx: summary", "82 min" in summ and ":" in summ)
    cp_bad = ContextProviders(extra={"boom": lambda: 1 / 0})
    snap_bad = cp_bad.snapshot()
    check("ctx: provider quebrado nao derruba", "boom" not in snap_bad)

    class FakeGLM:
        api_key = ""
    check("glm tools: None sem key",
          call_glm_with_tools(FakeGLM(), "oi", router) is None)
    st = router.stats()
    check("router: stats", st["calls_save"] >= 4 and st["calls_retrieve"] >= 1)

    print(f"\npersona_tools selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
