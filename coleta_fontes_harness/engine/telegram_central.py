"""Central Telegram opcional e read-only para o AURA Quant-X.

O módulo fica desativado por padrão. Quando explicitamente habilitado no
Windows, oferece apenas status, diagnóstico, catálogo de agentes, advisories e
consulta ao chat do Engine. Não existe shell, stop/restart, escrita, aprovação
ou execução de ferramenta neste canal.

Segredos nunca ficam no código: token, chat/user ID e PIN são variáveis de
ambiente. A aprovação de mudanças continua pertencendo ao control plane local.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


_TRUE = {"1", "true", "yes", "on"}
_MAX_MESSAGE = 3_700


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in _TRUE


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except (TypeError, ValueError):
        return default


def _env_id(name: str) -> str:
    return os.getenv(name, "").strip()


class AuraTelegramCentral:
    """Long polling opcional com superfície deliberadamente read-only."""

    def __init__(self, root: str | Path, *, api_call: Callable[..., Any] | None = None) -> None:
        self.root = Path(root)
        self.enabled = _env_bool("AURA_TELEGRAM_CENTRAL_ENABLED")
        self.token = os.getenv("AURA_TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self.authorized_chat_id = _env_id("AURA_TELEGRAM_CHAT_ID") or _env_id("TELEGRAM_CHAT_ID")
        self.authorized_user_id = _env_id("AURA_TELEGRAM_USER_ID")
        self.pin = os.getenv("AURA_TELEGRAM_PIN", "")
        self.session_ttl_s = _env_int("AURA_TELEGRAM_SESSION_TTL", 900, 60, 3600)
        self.min_interval_s = max(1.0, min(float(os.getenv("AURA_TELEGRAM_MIN_INTERVAL", "3")), 60.0))
        self.engine_url = os.getenv("AURA_TELEGRAM_ENGINE_URL", "http://127.0.0.1:8765").rstrip("/")
        self.api_base = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self._api_call = api_call or self._http_api_call
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset: int | None = None
        self._unlocked_until: dict[str, float] = {}
        self._last_request: dict[str, float] = {}
        self._lock = threading.RLock()
        self._last_error: str | None = None

    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self.enabled:
                return self.status()
            missing = [name for name, value in (("bot_token", self.token), ("chat_id", self.authorized_chat_id), ("user_id", self.authorized_user_id), ("pin", self.pin)) if not value]
            if missing:
                self._last_error = "missing_configuration:" + ",".join(missing)
                return self.status()
            if self._thread and self._thread.is_alive():
                return self.status()
            self._stop.clear()
            self._thread = threading.Thread(target=self._poll_loop, name="AURA-Telegram-ReadOnly", daemon=True)
            self._thread.start()
            return self.status()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            configured = bool(self.token and self.authorized_chat_id and self.pin)
            active = bool(self._thread and self._thread.is_alive())
            return {
                "enabled_by_env": self.enabled,
                "configured": configured,
                "active": active,
                "surface": "READ_ONLY_STATUS_DIAGNOSTIC_AGENTS_CHAT",
                "commands": ["/start", "/help", "/unlock", "/lock", "/status", "/diagnostic", "/agents", "/ask"],
                "mutation_commands": [],
                "execution_allowed": False,
                "paper_trade_only": True,
                "approval_required_for_mutation": True,
                "session_ttl_s": self.session_ttl_s,
                "last_error": self._last_error,
            }

    def _http_api_call(self, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_base:
            raise RuntimeError("telegram_not_configured")
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base}/{method}",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "AURA-Telegram-ReadOnly/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            document = json.loads(response.read().decode("utf-8", errors="replace"))
        if not isinstance(document, dict) or not document.get("ok"):
            raise RuntimeError("telegram_api_error")
        return document

    def _engine_request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.engine_url}/{path.lstrip('/')}"
        if payload is None:
            request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        else:
            request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.loads(response.read().decode("utf-8", errors="replace"))
        return value if isinstance(value, dict) else {"value": value}

    def _authorized(self, chat_id: str, user_id: str) -> bool:
        if not hmac.compare_digest(str(chat_id), self.authorized_chat_id):
            return False
        if self.authorized_user_id and not hmac.compare_digest(str(user_id), self.authorized_user_id):
            return False
        with self._lock:
            return time.time() < self._unlocked_until.get(str(chat_id), 0.0)

    def _rate_allowed(self, chat_id: str) -> bool:
        now = time.time()
        with self._lock:
            previous = self._last_request.get(str(chat_id), 0.0)
            if now - previous < self.min_interval_s:
                return False
            self._last_request[str(chat_id)] = now
            return True

    def _send(self, chat_id: str, text: str) -> None:
        self._api_call("sendMessage", {"chat_id": chat_id, "text": str(text)[:_MAX_MESSAGE], "disable_web_page_preview": True})

    def _json_message(self, title: str, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return f"{title}\n```\n{raw[-(_MAX_MESSAGE - len(title) - 8):]}\n```"

    def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict):
            return
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_id = str(chat.get("id", ""))
        user_id = str(sender.get("id", ""))
        text = str(message.get("text") or "").strip()
        if not chat_id or not text:
            return
        command, _, args = text.partition(" ")
        command = command.lower().split("@", 1)[0]
        if command in {"/start", "/help"}:
            self._send(chat_id, "AURA Telegram read-only. Use /unlock <PIN> e depois /status, /diagnostic, /agents ou /ask <pergunta>. Não há comandos remotos de escrita, parada ou execução.")
            return
        if command == "/unlock":
            if not hmac.compare_digest(chat_id, self.authorized_chat_id) or (self.authorized_user_id and not hmac.compare_digest(user_id, self.authorized_user_id)):
                self._send(chat_id, "Acesso negado.")
                return
            if hmac.compare_digest(args.strip(), self.pin):
                with self._lock:
                    self._unlocked_until[chat_id] = time.time() + self.session_ttl_s
                self._send(chat_id, "Sessão read-only desbloqueada por tempo limitado. Nenhuma alteração pode ser executada por este canal.")
            else:
                self._send(chat_id, "PIN incorreto.")
            return
        if command == "/lock":
            with self._lock:
                self._unlocked_until.pop(chat_id, None)
            self._send(chat_id, "Sessão bloqueada.")
            return
        if not self._authorized(chat_id, user_id):
            self._send(chat_id, "Sessão bloqueada. Use /unlock <PIN>.")
            return
        if not self._rate_allowed(chat_id):
            self._send(chat_id, "Aguarde alguns segundos antes da próxima consulta.")
            return
        try:
            if command == "/status":
                self._send(chat_id, self._json_message("AURA STATUS — somente leitura", self._engine_request("api/status")))
            elif command == "/diagnostic":
                self._send(chat_id, self._json_message("AURA DIAGNOSTIC — somente leitura", self._engine_request("api/diagnostics/deep")))
            elif command == "/agents":
                status = self._engine_request("api/agents/glm/status")
                advisories = self._engine_request("api/agents/glm/advisories?limit=5")
                self._send(chat_id, self._json_message("AURA AGENTS — advisory only", {"status": status, "advisories": advisories}))
            elif command == "/ask" and args.strip():
                answer = self._engine_request("api/trader/chat", {"message": args.strip()[:1000], "context": {}, "history": []})
                self._send(chat_id, self._json_message("AURA GLM — resposta advisory", answer))
            elif command == "/ask":
                self._send(chat_id, "Uso: /ask <pergunta>. A resposta passa pelo Engine local e não executa ações.")
            else:
                self._send(chat_id, "Comando não disponível. Esta Central aceita somente /status, /diagnostic, /agents e /ask; não aceita stop, restart, shell ou alterações.")
        except (urllib.error.URLError, TimeoutError, ValueError, RuntimeError, OSError) as exc:
            self._last_error = type(exc).__name__
            self._send(chat_id, "Consulta indisponível no momento; nenhuma ação foi executada.")

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                payload: dict[str, Any] = {"timeout": 10, "allowed_updates": ["message"]}
                if self._offset is not None:
                    payload["offset"] = self._offset
                result = self._api_call("getUpdates", payload)
                updates = result.get("result", []) if isinstance(result, dict) else []
                for update in updates if isinstance(updates, list) else []:
                    if isinstance(update, dict) and isinstance(update.get("update_id"), int):
                        self._offset = update["update_id"] + 1
                    self._handle_update(update)
            except Exception as exc:
                self._last_error = type(exc).__name__
                self._stop.wait(5)


__all__ = ["AuraTelegramCentral"]

