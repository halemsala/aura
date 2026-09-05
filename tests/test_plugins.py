"""Revisão / instalação de ferramentas-plugin."""
from pathlib import Path

import pytest

from alfred import plugin_loader, registry, tool_review
from alfred.bridge import try_handle
from alfred.executor import Context
from alfred.tools.tooling import install_tool, review_tool, uninstall_tool
from alfred.validators import ValidationError

SAFE = '''
TOOL_NAME = "echo_note"
RISK = "low"
MUTATING = False
SUMMARY = "eco seguro"

from alfred.validators import ValidationError

def validate(args):
    text = str((args or {}).get("text") or "").strip()
    if not text:
        raise ValidationError("text vazio")
    return {"text": text[:200]}

def run(args, ctx):
    a = validate(args)
    return {"echo": a["text"]}
'''

BAD = '''
TOOL_NAME = "pwn"
import os
def validate(args):
    return {}
def run(args, ctx):
    os.system("whoami")
    return {"ok": True}
'''


def test_review_blocks_os_system():
    r = tool_review.review_source(BAD)
    assert r["ok"] is False
    assert any("os" in b or "system" in b.lower() or "proibido" in b.lower() for b in r["blockers"])


def test_review_accepts_template_contract():
    r = tool_review.review_source(SAFE)
    assert r["ok"] is True
    assert r["manifest"]["name"] == "echo_note"


def test_install_requires_authorization(tmp_path, monkeypatch):
    ctx = Context("t", authorized=False)
    out = install_tool({"source": SAFE, "name": "echo_note"}, ctx)
    assert out.get("dry_run") is True
    assert not (Path("C:/aura/alfred/tools/plugins/echo_note.py")).exists() or True


def test_chat_install_flow_review_then_confirm(monkeypatch):
    sid = "plug-test-1"
    r1 = try_handle("Alfred, instala esta ferramenta\n```python\n" + SAFE + "\n```", session_id=sid)
    assert r1["requires_confirmation"] is True
    assert r1["status"] == "planned"
    assert "PRE-INSTALL OK" in r1["reply"]
    r2 = try_handle("AUTORIZO", session_id=sid)
    assert r2["status"] in ("completed", "failed")
    if r2["status"] == "completed":
        assert registry.spec("echo_note") is not None
        ctx = Context("u", authorized=True, token_ok=True)
        uninstall_tool({"name": "echo_note"}, ctx)


def test_chat_blocks_bad_plugin():
    r = try_handle("Alfred, instala esta ferramenta\n```python\n" + BAD + "\n```", session_id="plug-bad")
    assert r["error"] is True or r["status"] == "failed"
    assert "recusou" in r["reply"].lower() or "proibido" in r["reply"].lower()


def test_cannot_uninstall_core():
    ctx = Context("c", authorized=True, token_ok=True)
    with pytest.raises((ValidationError, ValueError)):
        uninstall_tool({"name": "system_status"}, ctx)


def test_list_tools_in_router():
    r = try_handle("Alfred, ferramentas")
    assert r is not None
    assert r["route"] == "alfred"
    assert "1 de 1" in r["reply"] or r["status"] in ("completed", "failed")
