#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_employee.py — o FUNCIONARIO no Telegram: comandos, conversa com a
persona, respostas em texto OU audio (voice note), canais com papeis,
entrega de arquivos (relatorios, prints) e alertas.

PAPEL vs telegram_hq original: este modulo ABSORVE o papel quando ativo —
UM TOKEN RODA UM POLLER SO. Nao rode os dois com o mesmo token.

CANAIS (engine/data/telegram_channels.json):
    [{"id": 123456, "role": "commands"}, {"id": -100999, "role": "alerts"}]
    commands: chat bidirecional (comandos + conversa + arquivos).
    alerts: so broadcast (o sistema posta alertas).

FLUXO DE UMA MENSAGEM (commands):
    /liberar <pin> | /status | /voz on|off | /auth <pin> -> internos
    senao: CommandCenter.handle_utterance (MESMA rota da voz) ->
    se None: chat da persona (voice server /api/voice/chat) ->
    resposta texto; se modo voz: TTS (/api/voice/tts) -> ffmpeg mp3->ogg
    -> sendVoice; sem ffmpeg: sendAudio; sem TTS: texto.
    Resultados com "path" de screenshot/print -> sendPhoto.

SEGURANCA:
    - chat_ids fora da lista: ignorados (log).
    - comandos exigem /auth <AURA_TG_PIN> (sessao 5 min, renova a cada uso).
    - desktop control: gate de mesa (DeskSession do desktop_controller) —
      /liberar usa AURA_DESK_PIN (diferente do PIN de chat).
    - alertas nao exigem auth (broadcast do sistema para o canal dono).

INTEGRACAO: hunks na resposta. Voice server: telegram.push_alert conecta
no CommandCenter; o CommandCenter e o mesmo da voz — um cerebro, duas bocas.
"""
from __future__ import annotations

import json
import logging
import os
import random
import shutil
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.telegram_emp")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]
_CHANNELS_PATH = _PROJ_ROOT / "engine" / "data" / "telegram_channels.json"
API = "https://api.telegram.org/bot%s/%s"
AUTH_TTL = 300.0


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


class TelegramAPI:
    """Cliente minimo da Bot API (urllib, multipart manual)."""

    def __init__(self, token: str):
        self._token = token
        self.calls = 0
        self.failures = 0

    def _call(self, method: str, data: Dict[str, Any],
              files: Optional[Dict[str, Tuple[str, bytes, str]]] = None
              ) -> Optional[dict]:
        url = API % (self._token, method)
        try:
            self.calls += 1
            if files:
                body, ctype = self._multipart(data, files)
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": ctype})
            else:
                req = urllib.request.Request(
                    url, data=urllib.parse.urlencode(data).encode("utf-8"))
            with urllib.request.urlopen(req, timeout=35) as resp:
                out = json.loads(resp.read().decode("utf-8",
                                                    errors="replace"))
                return out if out.get("ok") else None
        except Exception as exc:
            self.failures += 1
            logger.warning("telegram %s falhou: %s", method, exc)
            return None

    @staticmethod
    def _multipart(fields: Dict[str, Any],
                   files: Dict[str, Tuple[str, bytes, str]]):
        b = "----aura%d" % random.randint(100000000, 999999999)
        parts: List[bytes] = []
        for k, v in fields.items():
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n"
                 "\r\n%s\r\n" % (b, k, v)).encode("utf-8"))
        for k, (fname, blob, ctype) in files.items():
            parts.append(
                ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                 "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                 % (b, k, fname, ctype)).encode("utf-8"))
            parts.append(blob)
            parts.append(b"\r\n")
        parts.append(("--%s--\r\n" % b).encode("utf-8"))
        return b"".join(parts), "multipart/form-data; boundary=%s" % b

    # ---------------------------------------------------------- wrappers
    def send_message(self, chat_id: int, text: str) -> None:
        self._call("sendMessage", {"chat_id": chat_id, "text": text[:4000]})

    def send_voice(self, chat_id: int, ogg: bytes) -> None:
        self._call("sendVoice", {"chat_id": chat_id},
                   {"voice": ("voice.ogg", ogg, "audio/ogg")})

    def send_audio(self, chat_id: int, mp3: bytes, title: str = "") -> None:
        self._call("sendAudio", {"chat_id": chat_id, "title": title[:64]},
                   {"audio": ("fala.mp3", mp3, "audio/mpeg")})

    def send_photo(self, chat_id: int, blob: bytes,
                   fname: str = "tela.bmp") -> None:
        self._call("sendPhoto", {"chat_id": chat_id},
                   {"photo": (fname, blob, "image/bmp")})

    def send_document(self, chat_id: int, blob: bytes, fname: str) -> None:
        self._call("sendDocument", {"chat_id": chat_id},
                   {"document": (fname, blob, "application/octet-stream")})

    def get_updates(self, offset: int, timeout: int = 25) -> List[dict]:
        out = self._call("getUpdates", {"offset": offset,
                                        "timeout": timeout})
        return (out or {}).get("result") or []


class VoiceGateway:
    """Acesso ao voice server local (TTS + chat da persona)."""

    def __init__(self, base: str = "http://127.0.0.1:8099"):
        self.base = base.rstrip("/")

    def _post(self, path: str, payload: dict, timeout: float = 60) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                self.base + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8",
                                                     errors="replace"))
        except Exception as exc:
            logger.debug("voice gateway %s falhou: %s", path, exc)
            return None

    def tts_mp3(self, text: str) -> Optional[bytes]:
        out = self._post("/api/voice/tts", {"text": text[:1200]})
        if out and out.get("ok") and out.get("audio_base64"):
            import base64
            return base64.b64decode(out["audio_base64"])
        return None

    def chat(self, text: str, session_id: str) -> Optional[str]:
        out = self._post("/api/voice/chat",
                         {"text": text[:1500], "session_id": session_id})
        if out and out.get("ok"):
            return str(out.get("reply") or "")
        return None


def mp3_to_ogg_opus(mp3: bytes, ffmpeg: Optional[str] = None) -> Optional[bytes]:
    """Converte MP3 (edge-tts) para OGG/Opus (voice note). Sem ffmpeg: None."""
    ff = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
    if not ff:
        return None
    import subprocess
    with tempfile.TemporaryDirectory(prefix="aura_tg_") as td:
        src = Path(td) / "in.mp3"
        dst = Path(td) / "out.ogg"
        src.write_bytes(mp3)
        try:
            subprocess.run([ff, "-y", "-i", str(src), "-c:a", "libopus",
                            "-b:a", "48k", str(dst)],
                           capture_output=True, timeout=60, check=True)
            return dst.read_bytes()
        except Exception:
            logger.exception("mp3->ogg falhou")
            return None


class TelegramEmployee:
    """O funcionario no Telegram. Um poller por token."""

    def __init__(self, token: Optional[str] = None,
                 channels: Optional[List[dict]] = None,
                 command_center: Any = None,
                 voice: Optional[VoiceGateway] = None,
                 desk_gate: Any = None,
                 api: Optional[TelegramAPI] = None,
                 chat_pin: Optional[str] = None,
                 desk_pin: Optional[str] = None,
                 channels_path: Optional[Any] = None):
        self._token = (token if token is not None
                       else os.environ.get("AURA_TG_TOKEN", "")).strip()
        self._chat_pin = (chat_pin if chat_pin is not None
                          else os.environ.get("AURA_TG_PIN", "")).strip()
        self._desk_pin = (desk_pin if desk_pin is not None
                          else os.environ.get("AURA_DESK_PIN", "")).strip()
        self._api = api or TelegramAPI(self._token)
        self._cc = command_center
        self._voice = voice or VoiceGateway()
        self._gate = desk_gate
        self._channels = channels if channels is not None \
            else self._load_channels(channels_path or _CHANNELS_PATH)
        self._lock = threading.RLock()
        self._auth_until: Dict[int, float] = {}
        self._voice_mode: Dict[int, bool] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._offset = 0
        self.stats = {"processed": 0, "commands": 0, "chats": 0,
                      "auth_ok": 0, "auth_fail": 0, "desk_unlocks": 0,
                      "ignored_chats": 0, "voice_notes": 0,
                      "photos_sent": 0, "docs_sent": 0, "alerts_sent": 0}

    # ------------------------------------------------------------- canais
    def _load_channels(self, path) -> List[dict]:
        p = Path(path)
        try:
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [c for c in data if isinstance(c, dict)
                            and c.get("id") is not None]
        except Exception:
            logger.exception("channels ilegivel")
        # default: nenhum canal — o dono cria o arquivo
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps([
                {"id": 0, "role": "commands",
                 "note": "ponha seu chat_id (via /id no bot @userinfobot)"}],
                indent=1), encoding="utf-8")
        except OSError:
            pass
        return []

    def _chat_role(self, chat_id: int) -> Optional[str]:
        for c in self._channels:
            if int(c.get("id", -1)) == int(chat_id):
                return str(c.get("role", "commands"))
        return None

    def _commands_chat_ids(self) -> List[int]:
        return [int(c["id"]) for c in self._channels
                if str(c.get("role", "commands")) in ("commands", "both")]

    def _alerts_chat_ids(self) -> List[int]:
        return [int(c["id"]) for c in self._channels
                if str(c.get("role", "")) in ("alerts", "both")]

    # ------------------------------------------------------------- auth
    def _authed(self, chat_id: int) -> bool:
        with self._lock:
            return time.time() < self._auth_until.get(chat_id, 0)

    def _grant(self, chat_id: int) -> None:
        with self._lock:
            self._auth_until[chat_id] = time.time() + AUTH_TTL

    # ------------------------------------------------------------- ciclo
    def start(self) -> bool:
        if not self._token:
            logger.warning("telegram: AURA_TG_TOKEN ausente — funcionario off")
            return False
        if self._thread and self._thread.is_alive():
            return True
        if not any(c.get("id") for c in self._channels):
            logger.warning("telegram: nenhum canal com id valido "
                           "(telegram_channels.json) — funcionario off")
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="aura-telegram-emp")
        self._thread.start()
        logger.info("telegram funcionario ativo (%d canal/is)",
                    len(self._channels))
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                updates = self._api.get_updates(self._offset)
            except Exception:
                updates = []
            for upd in updates:
                try:
                    self._offset = max(self._offset,
                                       int(upd.get("update_id", 0)) + 1)
                    self._dispatch(upd)
                except Exception:
                    logger.exception("telegram: dispatch falhou")
            time.sleep(0.5)

    # ------------------------------------------------------------- dispatch
    def _dispatch(self, upd: dict) -> None:
        msg = upd.get("message") or upd.get("edited_message") or {}
        chat_id = msg.get("chat", {}).get("id")
        text = str(msg.get("text") or "").strip()
        if chat_id is None or not text:
            return
        role = self._chat_role(chat_id)
        if role is None:
            self.stats["ignored_chats"] += 1
            logger.warning("telegram: chat %s fora da lista — ignorado",
                           chat_id)
            return
        if role == "alerts":
            return  # canal de broadcast: mensagens do dono la sao ignoradas
        self.stats["processed"] += 1
        # gate de mesa: origem remota durante o processamento
        if self._gate is not None:
            self._gate.set_origin("remote")
        reply, extra = self._handle(chat_id, text)
        if self._gate is not None:
            self._gate.set_origin("local")
        if reply:
            self._reply(chat_id, reply, extra)

    def _handle(self, chat_id: int, text: str) -> Tuple[str, Optional[dict]]:
        low = _norm(text)
        # comandos internos
        if low.startswith("/start") or low.startswith("/comandos"):
            return ("Comandos: /auth <pin> liberar comandos · /status · "
                    "/voz on|off (responder com audio) · /liberar <pin da "
                    "mesa> (desktop por 10 min) · /relatorio (envia o "
                    "weekly_report) — ou converse/dite comandos do sistema "
                    "direto."), None
        if low.startswith("/auth"):
            pin = text.split(maxsplit=1)[1].strip() if " " in text else ""
            if self._chat_pin and pin == self._chat_pin:
                self._grant(chat_id)
                self.stats["auth_ok"] += 1
                return "Autenticado por 5 minutos.", None
            self.stats["auth_fail"] += 1
            return ("PIN incorreto (AURA_TG_PIN no PC).", None)
        if low.startswith("/voz"):
            on = "on" in low
            self._voice_mode[chat_id] = on
            return ("Respostas em audio %s." % ("ligadas" if on
                                                else "desligadas")), None
        if low.startswith("/liberar"):
            pin = text.split(maxsplit=1)[1].strip() if " " in text else ""
            if self._gate is None:
                return ("Gate de mesa indisponivel nesta build.", None)
            r = self._gate.authorize(pin)
            if r.get("ok"):
                self.stats["desk_unlocks"] += 1
            return r.get("speech", ""), None
        if low.startswith("/status"):
            st = self._cc.stats() if self._cc else {}
            return ("Funcionario online. Comandos processados: %d. "
                    "Mesa remota: %s."
                    % (self.stats["processed"],
                       "liberada" if (self._gate and self._gate.stats()[
                           "desk_session"]["active"]) else "bloqueada")), None
        if low.startswith("/relatorio"):
            rep = _PROJ_ROOT / "engine" / "data" / "weekly_report.md"
            if not rep.is_file():
                return ("Relatorio ainda nao gerado — diga 'rodar o "
                        "analytics' primeiro (por voz ou aqui)."), None
            try:
                self._api.send_document(chat_id, rep.read_bytes(),
                                        "weekly_report.md")
                self.stats["docs_sent"] += 1
                return "Relatorio enviado.", None
            except OSError as exc:
                return "Falha ao ler relatorio: %s" % exc, None
        # comandos do sistema: MESMA rota da voz
        if self._authed(chat_id) or not self._chat_pin:
            result = None
            if self._cc is not None:
                try:
                    result = self._cc.handle_utterance(text, "tg-%d" % chat_id)
                except Exception:
                    logger.exception("telegram: handle_utterance falhou")
            if result is not None:
                self.stats["commands"] += 1
                return result.get("speech", ""), result
            # nao era comando -> conversa com a persona (mesmo cerebro)
            reply = self._voice.chat(text, "tg-%d" % chat_id)
            if reply:
                self.stats["chats"] += 1
                return reply, None
            return ("Estou sem o cerebro agora (voice server fora?) — "
                    "comandos basicos continuam.", None)
        return ("Comandos exigem /auth <pin> primeiro.", None)

    # ------------------------------------------------------------- resposta
    def _reply(self, chat_id: int, text: str, extra: Optional[dict]) -> None:
        # print/screenshot no resultado -> enviar foto
        path = None
        if isinstance(extra, dict):
            p = extra.get("path") or (extra.get("detail") or {}).get("path")
            if isinstance(p, str) and p.endswith(".bmp"):
                path = p
        if path:
            try:
                blob = Path(path).read_bytes()
                self._api.send_photo(chat_id, blob, Path(path).name)
                self.stats["photos_sent"] += 1
            except OSError:
                logger.warning("telegram: print %s sumiu", path)
        if self._voice_mode.get(chat_id):
            mp3 = self._voice.tts_mp3(text)
            if mp3:
                ogg = mp3_to_ogg_opus(mp3)
                if ogg:
                    self._api.send_voice(chat_id, ogg)
                    self.stats["voice_notes"] += 1
                    return
                self._api.send_audio(chat_id, mp3, "AURA")
                self.stats["voice_notes"] += 1
                return
            logger.warning("telegram: TTS indisponivel — texto")
        self._api.send_message(chat_id, text)

    # ------------------------------------------------------------- alertas
    def push_alert(self, text: str) -> int:
        """Ligar no CommandCenter.push_alert para alertas falarem no canal."""
        n = 0
        for cid in self._alerts_chat_ids():
            self._api.send_message(cid, "[AURA] " + text[:3500])
            self.stats["alerts_sent"] += 1
            n += 1
        return n

    def stats_dict(self) -> dict:
        return {"telegram_employee": {
            "running": bool(self._thread and self._thread.is_alive()),
            "channels": len(self._channels),
            "chat_pin_required": bool(self._chat_pin),
            **self.stats}}


# ---------------------------------------------------------------------------
# self-test (sem rede real: API falsa)
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    class FakeAPI(TelegramAPI):
        def __init__(self):
            super().__init__("FAKE")
            self.sent: List[Tuple[str, dict]] = []
            self.updates: List[dict] = []

        def _call(self, method, data, files=None):
            self.sent.append((method, dict(data)))
            if method == "getUpdates":
                out, self.updates = self.updates, []
                return {"ok": True, "result": out}
            return {"ok": True, "result": {}}

        def send_voice(self, chat_id, ogg):
            self.sent.append(("sendVoice", {"chat_id": chat_id,
                                            "ogg_bytes": len(ogg)}))

        def send_photo(self, chat_id, blob, fname="t.bmp"):
            self.sent.append(("sendPhoto", {"chat_id": chat_id,
                                            "bytes": len(blob)}))

        def send_document(self, chat_id, blob, fname):
            self.sent.append(("sendDocument", {"chat_id": chat_id,
                                               "fname": fname}))

    # mp3->ogg sem ffmpeg no ambiente -> None (honesto)
    r = mp3_to_ogg_opus(b"ID3fake", ffmpeg="/inexistente/ffmpeg")
    check("ogg: sem ffmpeg -> None (degrada p/ audio)", r is None)

    # gateway com server falso
    class FakeVoice(VoiceGateway):
        def tts_mp3(self, text):
            return b"FAKEMP3" + text.encode("utf-8")[:10]

        def chat(self, text, session_id):
            return "persona respondeu: " + text[:20]

    with tempfile.TemporaryDirectory(prefix="aura_tg_st_") as td:
        ch_path = Path(td) / "channels.json"
        ch_path.write_text(json.dumps(
            [{"id": 111, "role": "commands"},
             {"id": -222, "role": "alerts"}]), encoding="utf-8")
        api = FakeAPI()
        emp = TelegramEmployee(token="T", channels_path=ch_path,
                               api=api, voice=FakeVoice(),
                               chat_pin="pin99", desk_pin="desk77")
        check("canais: carregados", len(emp._channels) == 2)
        check("canais: roles separadas",
              emp._commands_chat_ids() == [111]
              and emp._alerts_chat_ids() == [-222])

        # dispatch: chat fora da lista ignorado
        upd = {"update_id": 1, "message": {"chat": {"id": 999},
                                           "text": "/status"}}
        emp._dispatch(upd)
        check("seguranca: chat desconhecido ignorado",
              emp.stats["ignored_chats"] == 1 and api.sent == [])

        # sem auth -> comandos negados
        upd = {"update_id": 2, "message": {"chat": {"id": 111},
                                           "text": "status geral"}}
        emp._dispatch(upd)
        check("auth: sem /auth, comando negado",
              any("auth" in str(d.get("text", "")).lower()
                  for _m, d in api.sent if _m == "sendMessage"))

        # /auth errado e certo
        api.sent.clear()
        emp._dispatch({"update_id": 3, "message": {
            "chat": {"id": 111}, "text": "/auth errado"}})
        check("auth: PIN errado", emp.stats["auth_fail"] == 1)
        emp._dispatch({"update_id": 4, "message": {
            "chat": {"id": 111}, "text": "/auth pin99"}})
        check("auth: PIN certo concede",
              emp.stats["auth_ok"] == 1 and emp._authed(111))

        # comando de sistema via MESMA rota (CommandCenter fake)
        class FakeCC:
            def __init__(self):
                self.calls = []

            def handle_utterance(self, text, session):
                self.calls.append((text, session))
                if "status" in text.lower():
                    return {"speech": "Tudo operacional.", "tool": "fake"}
                return None

            def stats(self):
                return {}

        cc = FakeCC()
        emp._cc = cc
        api.sent.clear()
        emp._dispatch({"update_id": 5, "message": {
            "chat": {"id": 111}, "text": "status geral"}})
        check("comando: roteado ao CommandCenter",
              len(cc.calls) == 1 and cc.calls[0][1] == "tg-111")
        check("comando: resposta enviada",
              any("operacional" in str(d) for _m, d in api.sent))

        # conversa -> persona
        api.sent.clear()
        emp._dispatch({"update_id": 6, "message": {
            "chat": {"id": 111}, "text": "bom dia, como vai?"}})
        check("conversa: persona responde",
              any("persona" in str(d.get("text", ""))
                  for _m, d in api.sent if _m == "sendMessage"))

        # modo voz: TTS -> sem ffmpeg -> sendAudio
        emp._dispatch({"update_id": 7, "message": {
            "chat": {"id": 111}, "text": "/voz on"}})
        api.sent.clear()
        emp._dispatch({"update_id": 8, "message": {
            "chat": {"id": 111}, "text": "status geral"}})
        check("voz: audio enviado (fallback sendAudio)",
              any(m == "sendAudio" for m, _d in api.sent))
        emp._dispatch({"update_id": 9, "message": {
            "chat": {"id": 111}, "text": "/voz off"}})

        # gate de mesa: /liberar
        from desktop_controller import DeskSession
        gate = DeskSession(pin="desk77")
        emp._gate = gate
        emp._dispatch({"update_id": 10, "message": {
            "chat": {"id": 111}, "text": "/liberar errado"}})
        check("mesa: PIN errado negado", gate.stats()[
            "desk_session"]["remote_rejected_pin"] == 1)
        emp._dispatch({"update_id": 11, "message": {
            "chat": {"id": 111}, "text": "/liberar desk77"}})
        check("mesa: PIN certo libera", gate.stats()[
            "desk_session"]["active"] is True)
        check("mesa: origem volta a local apos dispatch",
              gate.origin == "local")

        # alerta broadcast
        n = emp.push_alert("feed silencioso 60s")
        check("alerta: postado no canal alerts", n == 1
              and any(d.get("chat_id") == -222
                      for m, d in api.sent if m == "sendMessage"))

        # /relatorio
        rep = _PROJ_ROOT / "engine" / "data" / "weekly_report.md"
        existed = rep.is_file()
        if not existed:
            rep.parent.mkdir(parents=True, exist_ok=True)
            rep.write_text("# rep teste", encoding="utf-8")
        api.sent.clear()
        emp._dispatch({"update_id": 12, "message": {
            "chat": {"id": 111}, "text": "/relatorio"}})
        check("relatorio: documento enviado",
              any(m == "sendDocument" for m, _d in api.sent))
        if not existed:
            try:
                rep.unlink()
            except OSError:
                pass

        st = emp.stats_dict()["telegram_employee"]
        check("stats: coerente", st["processed"] >= 8
              and st["commands"] >= 1 and st["chats"] >= 1)

        # start sem token
        emp2 = TelegramEmployee(token="", channels_path=ch_path)
        check("start: sem token nao sobe", emp2.start() is False)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - telegram_employee.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
