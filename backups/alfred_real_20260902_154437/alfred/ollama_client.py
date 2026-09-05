import requests
from .config import get_config


class OllamaError(RuntimeError):
    pass

class OllamaUnavailable(OllamaError):
    pass


class OllamaClient:
    """Adaptador Ollama. NUNCA faz fallback para outro modelo."""

    def __init__(self, cfg: dict = None):
        self.cfg = cfg or get_config()
        self.base = self.cfg["ollama_url"].rstrip("/")
        self.session = requests.Session()

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
        name = name or self.cfg["model"]
        wanted = name.split(":")[0]
        return any(m == name or m.split(":")[0] == wanted for m in self.installed_models())

    def chat(self, messages: list, temperature=None, num_predict=None, timeout=None) -> str:
        cfg = self.cfg
        payload = {
            "model": cfg["model"],
            "stream": False,
            "keep_alive": cfg["keep_alive"],
            "options": {
                "temperature": cfg["temperature"] if temperature is None else temperature,
                "num_ctx": cfg["num_ctx"],
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
                f"modelo '{cfg['model']}' não existe no Ollama (ver /api/tags). "
                "Não faço fallback silencioso para outro modelo.")
        r.raise_for_status()
        data = r.json()
        return (data.get("message") or {}).get("content", "")
