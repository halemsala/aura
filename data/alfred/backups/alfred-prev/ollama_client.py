import re
import requests
from .config import get_config


class OllamaError(RuntimeError):
    pass

class OllamaUnavailable(OllamaError):
    pass


_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
_EXCLUSIVE_MODEL = "qwen3:8b"


class OllamaClient:
    """Adaptador Ollama. NUNCA faz fallback para outro modelo."""

    def __init__(self, cfg: dict = None):
        self.cfg = cfg or get_config()
        self.base = self.cfg["ollama_url"].rstrip("/")
        self.session = requests.Session()
        self.model = self.cfg.get("model") or _EXCLUSIVE_MODEL
        if self.model != _EXCLUSIVE_MODEL:
            raise OllamaError(
                f"modelo configurado '{self.model}' recusado — exclusivo: {_EXCLUSIVE_MODEL}. "
                "Não faço fallback silencioso para outro modelo.")

    def tags(self, timeout: int = 5) -> dict:
        try:
            r = self.session.get(f"{self.base}/api/tags", timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise OllamaUnavailable(f"Ollama inacessível em {self.base}: {e}") from e

    def installed_models(self) -> list:
        return [m.get("name", "") for m in self.tags().get("models", [])]

    def has_model(self, name: str = None) -> bool:
        name = name or self.model
        return any(m == name for m in self.installed_models())

    def _split_thinking(self, data: dict) -> tuple:
        msg = data.get("message") or {}
        content = str(msg.get("content") or "")
        thinking = str(msg.get("thinking") or "")
        if "<think>" in content.lower():
            if not thinking:
                m = _THINK_RE.search(content)
                if m:
                    thinking = m.group(0)
            content = _THINK_RE.sub("", content)
        return content.strip(), thinking.strip()

    def chat(self, messages: list, temperature=None, num_predict=None, timeout=None) -> str:
        cfg = self.cfg
        try:
            from . import llm_cache
            hit = llm_cache.get(messages)
            if hit:
                return hit
        except Exception:
            pass
        payload = {
            "model": self.model,
            "messages": list(messages or []),
            "stream": False,
            "think": False,
            "keep_alive": cfg.get("keep_alive") or "-1",
            "options": {
                "temperature": cfg["temperature"] if temperature is None else temperature,
                "num_ctx": int(cfg.get("num_ctx") or 3072),
                "num_predict": cfg["num_predict"] if num_predict is None else num_predict,
                "num_gpu": 99,
            },
        }
        try:
            r = self.session.post(f"{self.base}/api/chat", json=payload,
                                  timeout=timeout or cfg["llm_timeout_s"])
        except requests.RequestException as e:
            raise OllamaUnavailable(f"falha a contactar o Ollama: {e}") from e
        if r.status_code == 404:
            raise OllamaError(
                f"modelo '{self.model}' não existe no Ollama (ver /api/tags). "
                "Não faço fallback silencioso para outro modelo.")
        if r.status_code >= 400:
            raise OllamaError(f"Ollama HTTP {r.status_code}: {(r.text or '')[:400]}")
        data = r.json()
        used = data.get("model") or self.model
        if used.split(":")[0] != "qwen3":
            raise OllamaError(
                f"Ollama devolveu modelo '{used}' em vez de {self.model}. "
                "Recuso fallback silencioso.")
        content, _thinking = self._split_thinking(data)
        try:
            from . import llm_cache
            llm_cache.put(messages, content)
        except Exception:
            pass
        return content
