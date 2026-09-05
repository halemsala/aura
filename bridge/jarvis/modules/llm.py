from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests


class LLM:
    def __init__(self, host, model, system_prompt, max_tokens, temperature, num_ctx=4096, runtime=None):
        self.host = host.rstrip("/")
        self.requested_model = str(model or "").strip()
        self.model = self.requested_model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.num_ctx = int(num_ctx or 4096)
        # runtime quant/GPU options (from device.recommend_llm_runtime)
        rt = dict(runtime or {})
        self.num_batch = int(rt.get("num_batch") or 256)
        self.num_gpu = int(rt.get("num_gpu") if rt.get("num_gpu") is not None else 99)
        self.runtime_profile = str(rt.get("profile") or "default")
        if rt.get("num_ctx"):
            self.num_ctx = int(rt["num_ctx"])
        if rt.get("temperature") is not None:
            self.temperature = float(rt["temperature"])
        self.sessions = {}  # session_id -> [messages]
        self.available_models = []
        self.last_error = None
        self.last_latency_ms = None
        self.last_ok = False
        self.model_checked_at = 0.0
        raw_fallbacks = os.getenv(
            "AURA_LLM_FALLBACK_MODELS",
            "llama3.2:3b,llama3.2:1b,qwen2.5:3b,phi3:mini",
        )
        self.fallback_models = [x.strip() for x in raw_fallbacks.split(",") if x.strip()]

    def _history(self, session_id: str, mood_instruction: str = ""):
        sid = session_id or "default"
        if sid not in self.sessions:
            self.sessions[sid] = [{"role": "system", "content": self.system_prompt}]
        history = self.sessions[sid]
        base = self.system_prompt.strip()
        history[0] = {"role": "system", "content": f"{base}\n\n{mood_instruction}".strip() if mood_instruction else base}
        return history

    def _trim(self, history):
        if len(history) > 8:
            return [history[0]] + history[-6:]
        return history

    @staticmethod
    def _with_context(user_text: str, context: str = "") -> str:
        if not context:
            return user_text
        return f"[CONTEXTO DO JOGO CARREGADO — USE COMO REFERÊNCIA ATUAL]\n{context}\n\n[MENSAGEM DO USUÁRIO]\n{user_text}"

    def _list_models(self, force: bool = False):
        now = time.time()
        if not force and now - self.model_checked_at < 5 and self.available_models:
            return self.available_models
        self.model_checked_at = now
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=3)
            resp.raise_for_status()
            data = resp.json() or {}
            names = []
            for item in data.get("models", []) or []:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("model")
                else:
                    name = str(item)
                if name:
                    names.append(str(name))
            self.available_models = sorted(set(names))
            return self.available_models
        except Exception as exc:
            self.last_error = f"Ollama indisponível: {exc}"
            self.last_ok = False
            self.available_models = []
            return []

    def ensure_model(self, force: bool = False) -> bool:
        names = self._list_models(force=force)
        if not names:
            return False
        candidates = [self.requested_model] + self.fallback_models
        for candidate in candidates:
            if not candidate:
                continue
            exact = next((name for name in names if name == candidate), None)
            if exact:
                if self.model != exact:
                    self.model = exact
                self.last_error = None
                self.last_ok = True
                return True
        self.last_error = (
            f"Modelo solicitado '{self.requested_model}' não está instalado; "
            f"modelos disponíveis: {', '.join(names[:8]) or 'nenhum'}"
        )
        self.last_ok = False
        return False

    def health(self) -> dict:
        return {
            "ok": bool(self.last_ok and self.model),
            "host": self.host,
            "requested_model": self.requested_model,
            "active_model": self.model,
            "available_models": self.available_models,
            "fallback_models": self.fallback_models,
            "last_error": self.last_error,
            "last_latency_ms": self.last_latency_ms,
            "runtime_profile": getattr(self, "runtime_profile", "default"),
            "num_ctx": getattr(self, "num_ctx", None),
            "num_batch": getattr(self, "num_batch", None),
            "num_gpu": getattr(self, "num_gpu", None),
            "temperature": getattr(self, "temperature", None),
        }

    def _unavailable_message(self) -> str:
        return (
            "O motor de IA local não está pronto. "
            + (self.last_error or "Verifique o Ollama e o modelo configurado.")
            + " Execute o diagnóstico AURA para ver a correção."
        )

    def ask(self, session_id: str, user_text: str, mood_instruction: str = "", context: str = "", max_tokens: Optional[int] = None) -> str:
        history = self._history(session_id, mood_instruction)
        predict_tokens = int(max_tokens or self.max_tokens)
        history.append({"role": "user", "content": self._with_context(user_text, context)})
        if not self.ensure_model():
            reply = self._unavailable_message()
            history.append({"role": "assistant", "content": reply})
            self.sessions[session_id or "default"] = self._trim(history)
            return reply
        payload = {
            "model": self.model, "messages": history, "stream": False,
            "options": {"temperature": self.temperature, "num_predict": predict_tokens, "num_ctx": self.num_ctx, "num_batch": self.num_batch, "num_gpu": self.num_gpu, "top_k": 30, "top_p": 0.9},
            "keep_alive": os.getenv("AURA_OLLAMA_KEEP_ALIVE", "0m"),
        }
        started = time.perf_counter()
        try:
            resp = requests.post(f"{self.host}/api/chat", json=payload, timeout=120)
            resp.raise_for_status()
            reply = resp.json().get("message", {}).get("content", "").strip()
            self.last_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.last_ok = bool(reply)
            self.last_error = None if reply else "Ollama retornou resposta vazia"
            if not reply:
                reply = self._unavailable_message()
        except Exception as exc:
            self.last_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.last_error = str(exc)
            self.last_ok = False
            reply = self._unavailable_message()
        history.append({"role": "assistant", "content": reply})
        self.sessions[session_id or "default"] = self._trim(history)
        return reply

    def ask_stream(self, session_id: str, user_text: str, mood_instruction: str = "", context: str = "", max_tokens: Optional[int] = None):
        history = self._history(session_id, mood_instruction)
        predict_tokens = int(max_tokens or self.max_tokens)
        history.append({"role": "user", "content": self._with_context(user_text, context)})
        if not self.ensure_model():
            reply = self._unavailable_message()
            history.append({"role": "assistant", "content": reply})
            self.sessions[session_id or "default"] = self._trim(history)
            yield reply
            return
        payload = {
            "model": self.model, "messages": history, "stream": True,
            "options": {"temperature": self.temperature, "num_predict": predict_tokens, "num_ctx": self.num_ctx, "num_batch": self.num_batch, "num_gpu": self.num_gpu, "top_k": 30, "top_p": 0.9},
            "keep_alive": os.getenv("AURA_OLLAMA_KEEP_ALIVE", "0m"),
        }
        full_reply = ""
        started = time.perf_counter()
        try:
            with requests.post(f"{self.host}/api/chat", json=payload, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line.decode("utf-8"))
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        full_reply += delta
                        yield delta
                    if chunk.get("done"):
                        break
            self.last_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.last_ok = bool(full_reply)
            self.last_error = None if full_reply else "Ollama retornou streaming vazio"
        except Exception as exc:
            self.last_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.last_error = str(exc)
            self.last_ok = False
            full_reply = self._unavailable_message()
            yield full_reply
        history.append({"role": "assistant", "content": full_reply})
        self.sessions[session_id or "default"] = self._trim(history)

    def reset_session(self, session_id: str):
        self.sessions.pop(session_id or "default", None)
