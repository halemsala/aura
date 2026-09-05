#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision.py — OLHAR sob demanda: screenshot -> Ollama (modelo multimodal
pequeno, ex. moondream:1.8b) -> descricao textual.

O QUE ENTREGA (honesto):
    - descrever a tela p/ contexto da persona (update_context {"vision":...})
    - VERIFICAR pos-acao: "o dialogo X apareceu?" -> sim/nao/nao sei
      (plugar no verify_fn do desktop_controller)
    - cache de 5s (nao martelar GPU por telefone repetido)

O QUE NAO FAZ: coordenadas de clique confiaveis — LLM pequeno nao acerta
pixel; deteccao com caixas e degrau futuro (qwen2-vl etc.). Nao finjo.

LIMITES: modelo multimodal precisa estar no Ollama (ollama pull
moondream:1.8b) — consome VRAM junto ao GLM-4 na 4050: use sob demanda
(ferramenta 'olhar'), nao vigilancia continua. Sem modelo/Ollama: resposta
honesta de indisponivel (nunca inventa o que 've').

INTEGRACAO: hunks na resposta. stdlib only. Windows. Console ASCII.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
import urllib.request
import unicodedata
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aura.vision")

__version__ = "1.0.0"
CACHE_TTL = 5.0


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


class VisionPerceiver:
    """Describe/verify via Ollama multimodal. Screenshot injetavel."""

    def __init__(self, ollama_url: str = "http://127.0.0.1:11434",
                 model: str = "moondream:1.8b",
                 shot_fn: Optional[Callable[[], Optional[bytes]]] = None,
                 post_fn: Optional[Callable[[str, dict], Optional[dict]]] = None,
                 cache_ttl: float = CACHE_TTL):
        self._url = ollama_url.rstrip("/")
        self._model = model
        self._shot = shot_fn  # devolve PNG/JPG/BMP bytes ou None
        self._post = post_fn or self._post_default
        self._ttl = float(cache_ttl)
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, Any]] = None
        self.stats = {"looks": 0, "cache_hits": 0, "failures": 0,
                      "no_shot": 0, "no_model": 0, "verifications": 0}

    # ------------------------------------------------------------ infra
    def _post_default(self, path: str, payload: dict) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                self._url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8",
                                                     errors="replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self.stats["no_model"] += 1
            return None
        except Exception:
            return None

    def _screenshot_b64(self) -> Optional[str]:
        if self._shot is None:
            self.stats["no_shot"] += 1
            return None
        try:
            blob = self._shot()
        except Exception:
            logger.exception("vision: screenshot falhou")
            return None
        if not blob:
            self.stats["no_shot"] += 1
            return None
        return base64.b64encode(blob).decode("ascii")

    def _ask(self, prompt: str, b64: str) -> Optional[str]:
        out = self._post("/api/generate", {
            "model": self._model, "prompt": prompt,
            "images": [b64], "stream": False, "keep_alive": "2m"})
        if not out or out.get("error"):
            return None
        return str(out.get("response") or "").strip()

    # ------------------------------------------------------------ api
    def look(self, prompt: str = "Descreva objetivamente o que aparece "
               "na tela em ate 3 frases, em portugues.") -> Dict[str, Any]:
        """Olha a tela AGORA (cache 5s) e descreve."""
        with self._lock:
            if self._cache and time.time() - self._cache["ts"] < self._ttl:
                self.stats["cache_hits"] += 1
                return dict(self._cache["result"], cached=True)
        b64 = self._screenshot_b64()
        if b64 is None:
            return {"ok": False,
                    "speech": "Sem captura de tela disponivel."}
        self.stats["looks"] += 1
        text = self._ask(prompt, b64)
        if text is None:
            self.stats["failures"] += 1
            return {"ok": False,
                    "speech": ("Visao indisponivel — verifique o Ollama e o "
                               "modelo (%s)." % self._model)}
        result = {"ok": True, "description": text,
                  "speech": text[:400]}
        with self._lock:
            self._cache = {"ts": time.time(), "result": result}
        return dict(result)

    def verify(self, question: str) -> Dict[str, Any]:
        """Pergunta sim/nao sobre a tela atual (verify_fn do desktop)."""
        self.stats["verifications"] += 1
        out = self.look("Olhe a tela e responda APENAS 'sim', 'nao' ou "
                        "'nao sei' para: %s" % question)
        if not out.get("ok"):
            return {"ok": False, "answer": None, "speech": out["speech"]}
        ans = _norm(out["description"])
        if ans.startswith("nao sei"):
            verdict = None  # incerteza explícita, não é um "não"
        elif ans.startswith("sim"):
            verdict = True
        elif ans.startswith("nao"):
            verdict = False
        else:
            verdict = None  # resposta não determinística
        return {"ok": True, "answer": verdict,
                "speech": ("verificado: %s" % ("sim" if verdict else
                                               "nao" if verdict is False
                                               else "incerto"))}

    def stats_dict(self) -> dict:
        return {"vision": dict(self.stats), "model": self._model}


# ---------------------------------------------------------------------------
# gramatica + tools
# ---------------------------------------------------------------------------
def parse_vision(utterance: str):
    import re
    t = _norm(utterance)
    if not t:
        return None
    if re.search(r"\b(?:olha|olhe|olhar|ve|ver)\s+(?:a\s+)?tela\b", t) \
            or t == "o que ta na tela":
        return ("olhar_tela", {})
    m = re.search(r"\b(?:confere|conferir|verifica|verificar)\s+"
                  r"(?:se\s+)?(.+)$", t)
    if m:
        return ("verificar_tela", {"pergunta": m.group(1).strip()})
    return None


def build_vision_tools(cc, vision: VisionPerceiver) -> None:
    cc.register("olhar_tela", "olhar a tela e descrever (modelo local)",
                lambda a, s: vision.look(), "read", confirm=False)
    cc.register("verificar_tela",
                "verificar sim/nao sobre a tela atual",
                lambda a, s: vision.verify(str(a.get("pergunta", ""))),
                "read", args={"pergunta": "pergunta sim/nao"}, confirm=False)


# ---------------------------------------------------------------------------
# self-test (sem Ollama: post_fn falso)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    class FakePost:
        def __init__(self, answer="A tela mostra o bloco de notas com o "
                                  "texto ola mundo."):
            self.answer = answer
            self.calls: List[dict] = []

        def __call__(self, path, payload):
            self.calls.append(payload)
            if path == "/api/generate":
                return {"response": self.answer}
            return None

    shots: List[bytes] = [b"FAKEIMG1", b"FAKEIMG2"]

    fp = FakePost()
    v = VisionPerceiver(shot_fn=lambda: shots.pop(0) if shots else None,
                        post_fn=fp, cache_ttl=1.0)
    r = v.look()
    check("look: descricao retornada", r["ok"] is True
          and "bloco de notas" in r["description"])
    check("look: payload com imagem b64",
          fp.calls and fp.calls[0]["images"][0].startswith("RkFLRUlNR"))
    r2 = v.look()
    check("look: cache de 5s evita nova captura",
          r2.get("cached") is True and v.stats["looks"] == 1)
    time.sleep(1.1)
    v.look()
    check("look: cache expira", v.stats["looks"] == 2)

    # verify: sim/nao/nao sei
    v2 = VisionPerceiver(shot_fn=lambda: b"IMG",
                         post_fn=FakePost("sim, o dialogo salvar esta aberto"),
                         cache_ttl=0.0)
    r = v2.verify("o dialogo salvar apareceu?")
    check("verify: sim parseado", r["answer"] is True)
    v3 = VisionPerceiver(shot_fn=lambda: b"IMG",
                         post_fn=FakePost("nao, nao aparece"),
                         cache_ttl=0.0)
    check("verify: nao parseado", v3.verify("x")["answer"] is False)
    v4 = VisionPerceiver(shot_fn=lambda: b"IMG",
                         post_fn=FakePost("nao sei dizer"),
                         cache_ttl=0.0)
    check("verify: incerto e None (nao inventa)",
          v4.verify("x")["answer"] is None)

    # sem screenshot / sem modelo: honesto
    v5 = VisionPerceiver(shot_fn=lambda: None, post_fn=fp, cache_ttl=0.0)
    check("sem shot: recusa honesta", v5.look()["ok"] is False
          and v5.stats["no_shot"] == 1)
    v6 = VisionPerceiver(shot_fn=lambda: b"IMG", cache_ttl=0.0,
                         post_fn=lambda p, d: None)
    r = v6.look()
    check("sem ollama: recusa honesta com dica",
          r["ok"] is False and "moondream" in r["speech"])

    # gramatica
    check("gram: olhar tela", parse_vision("olha a tela") ==
          ("olhar_tela", {}))
    check("gram: o que ta na tela", parse_vision("o que ta na tela") ==
          ("olhar_tela", {}))
    g = parse_vision("confere se o dialogo de salvar apareceu")
    check("gram: verificar", g == ("verificar_tela",
                                   {"pergunta":
                                    "o dialogo de salvar apareceu"}))
    check("gram: conversa comum", parse_vision("bom dia") is None)

    # tools no CommandCenter
    try:
        from jarvis_command_center import CommandCenter
    except Exception:
        CommandCenter = None  # type: ignore
    if CommandCenter is None:
        print("[SKIP] jarvis_command_center nao importavel aqui")
    else:
        cc = CommandCenter()
        build_vision_tools(cc, v)
        r = cc.execute("olhar_tela", {}, "u")
        check("cc: olhar_tela fala a descricao",
              r["ok"] is True and "bloco de notas" in r["speech"])
        cc_verify = CommandCenter()
        build_vision_tools(cc_verify, v2)
        r = cc_verify.execute("verificar_tela",
                              {"pergunta": "salvou?"}, "u")
        check("cc: verificar responde sim", r["ok"] is True
              and r.get("answer") is True)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - vision.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
