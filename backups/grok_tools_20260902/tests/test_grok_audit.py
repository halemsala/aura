"""Testes do audit Grok: router, BATs, circuit breaker, adapter, exclusividade qwen3:8b."""
import re
from pathlib import Path

import pytest

from alfred.circuit import allow, record_failure, record_success
from alfred.config import get_config
from alfred.hermes_adapter import is_candidate
from alfred.router import is_alfred_message, strip_prefix
from alfred.validators import ValidationError, resolve_allowed

ROOT = Path(__file__).resolve().parent.parent
BAT_ROOT = ROOT


def test_model_exclusive_qwen3():
    assert get_config()["model"] == "qwen3:8b"
    assert get_config()["services"]["hermes"]["port"] == 8777


def test_greeting_is_not_alfred():
    assert not is_alfred_message("olá")
    assert not is_alfred_message("Oi")
    assert not is_alfred_message("bom dia")
    assert not is_candidate("olá tudo bem?")
    assert is_candidate("Alfred, estado")
    assert is_candidate("Hermes, executa estado")
    assert is_candidate("AUTORIZO")
    assert is_candidate("CANCELA")


def test_hermes_executa_prefix():
    assert is_alfred_message("Hermes, executa abre exemplo.com")
    assert strip_prefix("Hermes, executa estado") == "estado"


def test_structured_try_handle_status():
    from alfred.bridge import try_handle
    r = try_handle("Alfred, estado")
    assert r["route"] == "alfred"
    assert r["model"] == "alfred:qwen3:8b"
    assert r["status"] in ("completed", "failed", "running")
    assert "plan" in r
    assert r.get("error") in (None, False) or "reply" in r


def test_project_root_is_allowed_windows_is_not():
    p = resolve_allowed(str(ROOT / "alfred" / "api.py"))
    assert p.exists()
    with pytest.raises(ValidationError):
        resolve_allowed(r"C:\Windows\System32\drivers\etc\hosts")


def test_circuit_breaker_opens():
    name = "test-circuit-unit"
    record_success(name)
    assert allow(name, max_failures=2, open_s=60, window_s=60)["allowed"] is True
    record_failure(name, max_failures=2, open_s=60, window_s=60)
    record_failure(name, max_failures=2, open_s=60, window_s=60)
    gate = allow(name, max_failures=2, open_s=60, window_s=60)
    assert gate["allowed"] is False
    record_success(name)
    assert allow(name, max_failures=2, open_s=60, window_s=60)["allowed"] is True


def test_bats_are_cmd_not_python():
    names = [
        "AURA_START_ALL.bat", "AURA_STOP_ALL.bat", "AURA_STATUS.bat",
        "AURA_OPEN_CHAT.bat", "AURA_ALFRED_COMMAND.bat", "AURA_ROLLBACK_LAST.bat",
        "FINALIZAR_AURA_ALFRED_QWEN3.bat",
    ]
    py_line = re.compile(r"^\s*(try:|from alfred|import |```python|# PROMPT)", re.I)
    for name in names:
        p = BAT_ROOT / name
        assert p.is_file(), name
        text = p.read_text(encoding="utf-8", errors="replace")
        assert text.lstrip().lower().startswith("@echo off") or "@echo off" in text[:80].lower()
        for i, line in enumerate(text.splitlines(), 1):
            assert not py_line.match(line), f"{name}:{i} parece Python/Markdown: {line}"


def test_alfred_has_no_autorun_startfile():
    for p in (ROOT / "alfred").rglob("*.py"):
        src = p.read_text(encoding="utf-8", errors="replace")
        assert "os.startfile" not in src, p
        assert "webbrowser.open" not in src or p.name == "open_url.py"


def test_no_silent_model_fallback_in_alfred():
    for p in (ROOT / "alfred").rglob("*.py"):
        src = p.read_text(encoding="utf-8", errors="replace")
        assert "llama3.2:3b" not in src, p
        assert "qwen2.5:3b" not in src, p
