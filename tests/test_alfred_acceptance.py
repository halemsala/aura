# Testes 1 e 2 do prompt — inferência real. Se o Ollama não estiver acessível,
# ficam marcados como SKIP com reason="BLOCKED_OLLAMA" (nunca sucesso inventado).
import pytest, requests

from alfred.config import get_config


def _ollama_up():
    try:
        return requests.get(get_config()["ollama_url"] + "/api/tags", timeout=3).ok
    except requests.RequestException:
        return False


@pytest.mark.skipif(not _ollama_up(), reason="BLOCKED_OLLAMA — Ollama não acessível neste ambiente")
def test_qwen3_in_tags():
    r = requests.get(get_config()["ollama_url"] + "/api/tags", timeout=5).json()
    names = [m.get("name", "") for m in r.get("models", [])]
    assert any(n.split(":")[0] == "qwen3" for n in names), f"qwen3:8b ausente em {names}"


@pytest.mark.skipif(not _ollama_up(), reason="BLOCKED_OLLAMA — Ollama não acessível neste ambiente")
def test_real_chat_responds_with_model():
    from alfred.ollama_client import OllamaClient, OllamaError
    try:
        out = OllamaClient().chat([{"role": "user", "content": "Responde apenas: OK"}], num_predict=16)
    except OllamaError as e:
        pytest.fail(f"modelo ausente/mal configurado: {e}")
    assert isinstance(out, str) and len(out.strip()) > 0


@pytest.mark.skipif(not _ollama_up(), reason="BLOCKED_OLLAMA")
def test_end_to_end_plan_and_authorize(monkeypatch):
    import webbrowser
    from alfred.bridge import try_handle
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda u, new=0: calls.append(u) or True)
    r1 = try_handle("Alfred, abre três pesquisas sobre automação com IA")
    assert r1["requires_confirmation"] is True
    assert r1["plan"]["intent"] == "search_multi" and len(r1["plan"]["tasks"]) == 3
    assert len(calls) == 0                          # nada aberto antes de AUTORIZO
    r2 = try_handle("AUTORIZO")
    assert "3 de 3" in r2["reply"] and len(calls) == 3
