from alfred.flags import load_flags, save_flags
from alfred.bridge import try_handle
from alfred.executor import Context
from alfred.tools.repair_voice import set_aura_flag, vram_capacity
from alfred.tools.observe import observe_pc
from alfred.voice_win import _sanitize


def test_flags_default_paper_on():
    fl = load_flags()
    assert fl.get("execution_allowed") is False


def test_sanitize_strips_injection():
    s = _sanitize("ola; Remove-Item -Recurse C:\\ & notepad")
    assert "&" not in s
    assert "$" not in s


def test_set_paper_trade_dry():
    r = set_aura_flag({"flag": "paper_trade", "value": False}, Context("t", authorized=False))
    assert r.get("dry_run") is True


def test_observe_pc_shape():
    r = observe_pc({}, Context("o", authorized=False))
    assert "foreground_window" in r or r.get("blocked")


def test_vram_capacity_shape():
    r = vram_capacity({}, Context("v", authorized=False))
    assert "recommended_num_ctx" in r
    assert r.get("ready_for_more_vram") is True


def test_router_paper_off_needs_auth():
    r = try_handle("Alfred, desativa paper_trade")
    assert r is not None
    assert r.get("requires_confirmation") is True


def test_supervise_module_imports():
    from alfred import supervise
    assert supervise.INTERVAL >= 5
    assert 11434 not in (8791, 8777)


def test_corrige_explains_when_repair_off():
    r = try_handle("Alfred, corrige")
    assert r is not None
    assert r.get("status") == "blocked"
    assert "paper_trade" in r["reply"]
