#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Telegram HQ: bot com 2FA (PIN) para ler logs,
status da GPU e autorizar mudancas pelo celular. Usa urllib (stdlib)
para a API do Telegram.

Seguranca:
  - Token via env AURA_TG_TOKEN (ou SecureStorage no Desktop)
  - PIN obrigatorio para comandos de acao
  - Comandos de leitura (status, logs) sem PIN
  - allowed_chat_ids restringe quem pode falar com o bot
"""
from __future__ import annotations
import json
import logging
import os
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger("aura.telegram")
__version__ = "1.0.0"
__all__ = ["TelegramHQ"]

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramHQ:
    """Bot Telegram long-polling com 2FA."""

    def __init__(self, token: Optional[str] = None, *,
                 pin: Optional[str] = None,
                 allowed_chat_ids: Optional[List[int]] = None,
                 poll_interval: float = 2.0,
                 timeout: float = 10.0):
        self.token = token or os.getenv("AURA_TG_TOKEN", "")
        self.pin = str(pin) if pin else os.getenv("AURA_TG_PIN", "")
        self.allowed_chats = set(int(x) for x in (allowed_chat_ids or []))
        self.poll_interval = float(poll_interval)
        self.timeout = float(timeout)
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._authed: Dict[int, float] = {}
        self._auth_ttl = 300.0
        self._offset = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sent = 0
        self._received = 0

    def register_command(self, cmd: str,
                          handler: Callable[[], Dict[str, Any]],
                          *, require_pin: bool = False,
                          description: str = "") -> None:
        self._commands[cmd.lower()] = {"fn": handler, "pin": require_pin,
                                        "desc": description}

    def send_message(self, chat_id: int, text: str) -> bool:
        if not self.token:
            return False
        try:
            data = json.dumps({"chat_id": chat_id, "text": text[:4096],
                                "parse_mode": "Markdown"}).encode()
            req = urllib.request.Request(
                _API.format(token=self.token, method="sendMessage"),
                data=data,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._sent += 1
                return r.status == 200
        except Exception as e:
            log.error("[telegram] send falhou: %s", e)
            return False

    def _get_updates(self) -> list:
        if not self.token:
            return []
        try:
            data = json.dumps({"offset": self._offset,
                                "timeout": 1}).encode()
            req = urllib.request.Request(
                _API.format(token=self.token, method="getUpdates"),
                data=data,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout + 5) as r:
                return json.loads(r.read()).get("result", [])
        except Exception:
            return []

    def _handle(self, chat_id: int, text: str) -> None:
        self._received += 1
        if self.allowed_chats and chat_id not in self.allowed_chats:
            self.send_message(chat_id, "Chat nao autorizado.")
            return
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "auth":
            if not self.pin:
                self.send_message(chat_id, "PIN nao configurado.")
                return
            if args == self.pin:
                self._authed[chat_id] = time.time() + self._auth_ttl
                self.send_message(chat_id, "Autenticado por 5 min.")
            else:
                self.send_message(chat_id, "PIN incorreto.")
            return

        if cmd == "help":
            lines = ["*Comandos:*"]
            for c, info in sorted(self._commands.items()):
                tag = " [PIN]" if info["pin"] else ""
                lines.append(f"`/{c}`{tag} — {info['desc']}")
            lines.append("`/auth <pin>` — autenticar")
            self.send_message(chat_id, "\n".join(lines))
            return

        entry = self._commands.get(cmd)
        if entry is None:
            self.send_message(chat_id, f"Comando `/{cmd}` desconhecido. Use /help.")
            return
        if entry["pin"]:
            if time.time() > self._authed.get(chat_id, 0):
                self.send_message(chat_id,
                    "Comando exige PIN. Use `/auth <pin>`.")
                return
        try:
            result = entry["fn"]() or {}
            self.send_message(chat_id, str(result.get("text", "ok")))
        except Exception as e:
            self.send_message(chat_id, f"Erro: {e}")

    def start(self) -> "TelegramHQ":
        if not self.token:
            log.warning("[telegram] sem token — bot inativo")
            return self
        if self._running:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._loop,
                                        name="telegram-hq", daemon=True)
        self._thread.start()
        log.info("[telegram] HQ ativo")
        return self

    def _loop(self) -> None:
        while self._running:
            try:
                for u in self._get_updates():
                    self._offset = max(self._offset,
                                       (u.get("update_id") or 0) + 1)
                    msg = u.get("message") or {}
                    cid = msg.get("chat", {}).get("id")
                    txt = msg.get("text", "")
                    if cid and txt:
                        self._handle(int(cid), txt)
            except Exception:
                log.exception("[telegram] loop falhou")
            time.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False

    def stats(self) -> dict:
        return {"running": self._running, "sent": self._sent,
                "received": self._received,
                "commands": len(self._commands),
                "authed_chats": len(self._authed)}


if __name__ == "__main__":
    import sys
    errs = []
    def check(n, c, x=""):
        print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {x}" if x else ""))
        if not c: errs.append(n)

    # Teste offline (sem token real)
    tg = TelegramHQ(token=None, pin="1234", allowed_chat_ids=[99999])
    tg.register_command("status", lambda: {"text": "OK"},
                         require_pin=False, description="status")
    tg.register_command("restart", lambda: {"text": "reiniciando"},
                         require_pin=True, description="restart")
    check("registra 2 comandos", tg.stats()["commands"] == 2)
    check("restart exige PIN", tg._commands["restart"]["pin"] is True)
    tg.start()
    check("sem token: nao inicia", tg.stats()["running"] is False)

    # Handler direto
    calls = []
    def h():
        calls.append(1)
        return {"text": "OK"}
    tg2 = TelegramHQ(token=None, pin="x", allowed_chat_ids=[123])
    tg2.register_command("ping", h, require_pin=False)
    r = h()
    check("handler executa", r["text"] == "OK" and len(calls) == 1)

    print(f"\ntelegram_hq selftest: {len(errs)} falha(s)")
    sys.exit(1 if errs else 0)
