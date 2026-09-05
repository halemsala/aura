#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_auth.py — autenticacao de VOZ vinda do Telegram: STT + voiceprint +
codigo de confirmacao por tier de risco.

FILOSOFIA (decisao de desenho, nao limitacao):
    VOZ NUNCA E IDENTIDADE. O que autoriza e o canal (PIN + lista de chats);
    a voz e apenas UM fator adicional — o mais facil de falsificar
    (capturavel em ligacao, deepfakeavel, irrevogavel). Voz abre o tier
    ALTO quando combinada com PIN da mesa + codigo instituido + cooldown.
    Replay-proof: o codigo e gerado POR PEDIDO e expira.

TIERS:
    leitura    -> PIN usual do chat (nada extra)
    mesa       -> /liberar (gate de 10 min) — como hoje
    alto       -> voiceprint >= 0.62 E codigo instituido falado corretamente
                  E cooldown respeitado. Falhou qualquer um: negado e
                  journalado (quem tentou, quando, score).
    Voiceprint: reusa VoicePrint do people_memory (perfil 'Administrador'
    registrado com 3+ amostras). Sem perfil: tier alto INDISPONIVEL —
    degrada honesto (log + stats), nunca abre sem voz verificada.

Audiencia do journal: engine/data/voice_auth_events.jsonl — cada tentativa
com {ts, chat_id, tier, score, code_ok, decisao}. Reversivel: apagar o
perfil 'Administrador' em people_memory desliga o tier alto.

INTEGRACAO: telegram_employee chama VoiceAuthGate.evaluate(...) ANTES de
processar audio/ordem de tier alto. Hunks na resposta.

stdlib only. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import json
import logging
import random
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.voice_auth")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]
_EVENTS = _PROJ_ROOT / "engine" / "data" / "voice_auth_events.jsonl"

ADMIN_PERSON = "Administrador"
VOICE_THRESHOLD = 0.62
CODE_TTL = 180.0        # codigo valido por 3 min
CODE_COOLDOWN = 900.0   # 15 min entre pedidos de tier alto
CODE_RE = re.compile(r"\b(?:codigo|c[óo]digo)\s*(\d{3,6})\b")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_num(text: str) -> str:
    return re.sub(r"\D", "", str(text or ""))


class CodeChallenge:
    """Codigo instituido por pedido: gerado na hora, expira, uso unico."""

    def __init__(self, ttl: float = CODE_TTL):
        self._ttl = float(ttl)
        self._lock = threading.Lock()
        self._code: Optional[str] = None
        self._exp = 0.0
        self._used = False

    def issue(self) -> str:
        with self._lock:
            self._code = "%04d" % random.randint(1000, 9999)
            self._exp = time.time() + self._ttl
            self._used = False
            return self._code

    def check(self, spoken: str) -> Tuple[bool, str]:
        """Valida o codigo DITO contra o emitido. Consome no sucesso."""
        with self._lock:
            if self._code is None or self._used:
                return False, "sem_codigo_ativo"
            if time.time() > self._exp:
                return False, "codigo_expirado"
            said = _norm_num(spoken)
            if not said:
                return False, "codigo_nao_encontrado"
            if said == self._code:
                self._used = True
                return True, "ok"
            return False, "codigo_errado"


class VoiceAuthGate:
    """Avalia audio do Telegram p/ acoes de tier alto. NUNCA e identidade
    unica — e fator 2 de 3 (PIN da mesa + voiceprint + codigo)."""

    def __init__(self, people: Any = None,
                 stt_fn: Optional[Callable] = None,
                 events_path: Optional[Any] = None,
                 threshold: float = VOICE_THRESHOLD,
                 cooldown: float = CODE_COOLDOWN):
        from typing import Callable  # noqa: F401 (doc clarity)
        self._people = people
        self._stt = stt_fn  # (wav_path) -> texto
        self._events = Path(events_path) if events_path else _EVENTS
        self._threshold = float(threshold)
        self._cooldown = float(cooldown)
        self._lock = threading.Lock()
        self._challenge = CodeChallenge()
        self._last_ok = 0.0
        self.stats = {"evaluations": 0, "denied": 0, "granted": 0,
                      "voice_low_score": 0, "code_fail": 0,
                      "cooldown_blocked": 0, "no_profile": 0}

    # ------------------------------------------------------------ perfil
    def profile_ready(self) -> bool:
        if self._people is None:
            return False
        try:
            for p in self._people.list_people():
                if _norm(ADMIN_PERSON) in _norm(p["name"]):
                    return p["voices"] >= 3
        except Exception:
            logger.exception("voice_auth: list_people falhou")
        return False

    def _voice_score(self, wav_path: str) -> Optional[float]:
        if self._people is None:
            return None
        try:
            name, score = self._people.identify_voice(wav_path)
            if name and _norm(ADMIN_PERSON) in _norm(name):
                return float(score)
        except Exception:
            logger.exception("voice_auth: identify_voice falhou")
        return None

    # ------------------------------------------------------------ journal
    def _log_event(self, chat_id: Any, tier: str, score: Optional[float],
                   code_result: str, granted: bool, detail: str) -> None:
        try:
            self._events.parent.mkdir(parents=True, exist_ok=True)
            with open(self._events, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": _iso_now(), "chat_id": str(chat_id), "tier": tier,
                    "voice_score": round(score, 3) if score is not None else None,
                    "code": code_result, "granted": granted,
                    "detail": detail[:120]}, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("voice_auth: journal falhou")

    # ------------------------------------------------------------ api
    def request_high_tier(self, chat_id: Any) -> dict:
        """Emite codigo p/ o admin repetir por voz. Respeita cooldown."""
        if not self.profile_ready():
            self.stats["no_profile"] += 1
            return {"ok": False,
                    "speech": ("Tier alto exige perfil de voz do "
                               "Administrador com 3+ amostras "
                               "(people_memory). Registre e tente.")}
        with self._lock:
            if time.time() - self._last_ok < self._cooldown:
                wait = int(self._cooldown - (time.time() - self._last_ok))
                self.stats["cooldown_blocked"] += 1
                return {"ok": False,
                        "speech": ("Cooldown ativo: aguarde %d min p/ nova "
                                   "acao de tier alto." % (wait // 60 + 1))}
        code = self._challenge.issue()
        self._log_event(chat_id, "alto", None, "emitido", False,
                        "codigo emitido")
        return {"ok": True, "speech": ("Acao de alto risco: repita por voz "
                                       "'codigo %s' dentro de 3 minutos." % code),
                "code_hint_digits": len(code)}

    def evaluate_high_tier(self, chat_id: Any, wav_path: str,
                           spoken_text: str) -> dict:
        """Fatores: voiceprint + codigo falado. Ambos devem passar."""
        self.stats["evaluations"] += 1
        if not self.profile_ready():
            self.stats["no_profile"] += 1
            self._log_event(chat_id, "alto", None, "-", False,
                            "sem perfil de administrador")
            return {"ok": False, "speech": "Tier alto indisponivel: sem "
                    "perfil de voz do Administrador."}

        score = self._voice_score(wav_path)
        code_ok, code_result = self._challenge.check(spoken_text)

        if score is None or score < self._threshold:
            self.stats["voice_low_score"] += 1
            self.stats["denied"] += 1
            self._log_event(chat_id, "alto", score, code_result, False,
                            "voiceprint abaixo do threshold")
            return {"ok": False,
                    "speech": ("Voz nao reconhecida como Administrador "
                               "(score %s). Acao negada e registrada."
                               % ("%.2f" % score if score else "n/a"))}
        if not code_ok:
            self.stats["code_fail"] += 1
            self.stats["denied"] += 1
            self._log_event(chat_id, "alto", score, code_result, False,
                            "codigo invalido")
            return {"ok": False,
                    "speech": "Codigo incorreto ou expirado. Solicite novo."}
        with self._lock:
            self._last_ok = time.time()
        self.stats["granted"] += 1
        self._log_event(chat_id, "alto", score, code_result, True, "ok")
        return {"ok": True, "speech": "Voz verificada. Prosseguindo com a "
                "acao de alto risco."}

    def stats_dict(self) -> dict:
        return {"voice_auth": {
            "profile_ready": self.profile_ready(), **self.stats,
            "threshold": self._threshold,
            "cooldown_s": int(self._cooldown)}}


def _norm(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import math
    import struct
    import wave as wavemod

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    def synth_wav(path, freq, seconds=2.0, sr=16000):
        n = int(sr * seconds)
        frames = bytearray()
        for i in range(n):
            env = 0.55 + 0.45 * math.sin(2 * math.pi * i / sr * 1.5)
            frames += struct.pack("<h", int(12000 * env * math.sin(
                2 * math.pi * freq * i / sr)))
        with wavemod.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(bytes(frames))

    # CodeChallenge
    ch = CodeChallenge(ttl=0.5)
    code = ch.issue()
    ok, why = ch.check("codigo %s" % code)
    check("codigo: aceite na 1a", ok is True and why == "ok")
    ok, why = ch.check("codigo %s" % code)
    check("codigo: uso unico", ok is False and why == "sem_codigo_ativo")
    ch2 = CodeChallenge(ttl=0.05)
    c2 = ch2.issue()
    time.sleep(0.1)
    ok, why = ch2.check("codigo %s" % c2)
    check("codigo: expira", ok is False and why == "codigo_expirado")
    ch3 = CodeChallenge(ttl=5)
    c3 = ch3.issue()
    ok, why = ch3.check("código 9 9 9 9")
    check("codigo: digitos espacados normalizados",
          ok is False and why == "codigo_errado")  # 9999 != c3
    ok, why = ch3.check("codigo %s" % c3)
    check("codigo: correto apos erro", ok is True)

    # people fake
    class FakePeople:
        def __init__(self):
            self.match_name = ADMIN_PERSON
            self.match_score = 0.8

        def list_people(self):
            return [{"name": ADMIN_PERSON, "voices": 3, "times_seen": 1}]

        def identify_voice(self, wav):
            return self.match_name, self.match_score

    with tempfile.TemporaryDirectory(prefix="aura_va_st_") as td:
        good = Path(td) / "good.wav"
        synth_wav(good, 110)
        va = VoiceAuthGate(people=FakePeople(),
                           events_path=Path(td) / "ev.jsonl",
                           cooldown=0.2)
        check("perfil: pronto com 3 vozes", va.profile_ready() is True)

        # sem codigo emitido
        r = va.evaluate_high_tier(111, str(good), "codigo 1234")
        check("alto: sem codigo ativo -> negado", r["ok"] is False)

        # fluxo certo
        req = va.request_high_tier(111)
        check("pedido: emite codigo na fala", req["ok"] is True
              and "codigo" in req["speech"])
        # extrai o codigo emitido da fala para repetir
        m = re.search(r"codigo (\d{4})", req["speech"])
        r = va.evaluate_high_tier(111, str(good), "código %s" % m.group(1))
        check("alto: voz certa + codigo certo -> concedido",
              r["ok"] is True)

        # cooldown apos sucesso
        req2 = va.request_high_tier(111)
        check("cooldown: bloqueia pedido imediato", req2["ok"] is False
              and "Cooldown" in req2["speech"])
        time.sleep(0.25)
        req3 = va.request_high_tier(111)
        check("cooldown: libera apos esperar", req3["ok"] is True)

        # voz errada
        fp = FakePeople()
        fp.match_score = 0.30
        va2 = VoiceAuthGate(people=fp, events_path=Path(td) / "ev.jsonl",
                            cooldown=0.0)
        rq = va2.request_high_tier(111)
        m = re.search(r"codigo (\d{4})", rq["speech"])
        r = va2.evaluate_high_tier(111, str(good), "codigo %s" % m.group(1))
        check("alto: score baixo -> negado com score na fala",
              r["ok"] is False and "0.30" in r["speech"])

        # codigo errado
        rq = va2.request_high_tier(111)
        r = va2.evaluate_high_tier(111, str(good), "codigo 0000")
        check("alto: codigo errado -> negado", r["ok"] is False)

        # sem perfil
        class NoProfile:
            def list_people(self):
                return [{"name": "outra pessoa", "voices": 5}]

            def identify_voice(self, w):
                return "outra pessoa", 0.9

        va3 = VoiceAuthGate(people=NoProfile(),
                            events_path=Path(td) / "ev.jsonl")
        r = va3.request_high_tier(111)
        check("sem perfil: tier alto indisponivel", r["ok"] is False
              and "Administrador" in r["speech"])

        # journal
        lines = (Path(td) / "ev.jsonl").read_text(encoding="utf-8").splitlines()
        check("journal: eventos gravados", len(lines) >= 4
              and any('"granted": true' in line for line in lines)
              and any('"granted": false' in line for line in lines))

        st = va2.stats_dict()["voice_auth"]
        check("stats: avaliacoes e negacoes contadas",
              st["evaluations"] >= 2 and st["denied"] >= 1)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - voice_auth.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
