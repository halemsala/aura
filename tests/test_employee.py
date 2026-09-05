from pathlib import Path

import pytest

from alfred.bridge import try_handle
from alfred.executor import Context
from alfred.focus_mode import PAUSABLE, PROTECTED_PORTS
from alfred.gpu_share.worker import games_running, nvidia
from alfred.tools.apps import list_apps
from alfred.tools.files import delete_file, preview_change
from alfred.tools.gpu_share_tools import _v_reg
from alfred.tools.skills_search import search_skill
from alfred.validators import ValidationError, resolve_allowed


def test_windows_system_still_blocked():
    with pytest.raises(ValidationError):
        resolve_allowed(r"C:\Windows\System32\notepad.exe")
    with pytest.raises(ValidationError):
        resolve_allowed(r"C:\Windows\SysWOW64\cmd.exe")
    with pytest.raises(ValidationError):
        resolve_allowed(r"C:\Program Files\Windows NT\Accessories\wordpad.exe")


def test_hid_requires_autorizo():
    from alfred.tools.hid import mouse_click, key_press
    r = mouse_click({}, Context("h", authorized=False))
    assert r.get("dry_run") is True
    r2 = key_press({"keys": "enter"}, Context("h", authorized=False))
    assert r2.get("dry_run") is True


def test_human_summary_does_not_say_one_of_one():
    from alfred.executor import human_summary
    job = {
        "status": "success",
        "tasks": [{
            "tool": "system_status", "status": "success",
            "result": {"cpu_percent": 10, "ram_used_pct": 40, "gpu": {"name": "RTX"},
                       "ollama": {"online": True, "model_present": True}},
        }],
    }
    s = human_summary(job)
    assert "1 de 1" not in s
    assert "Ollama" in s or "CPU" in s


def test_stt_rejects_lexicon_hallucination():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(r"C:\aura\bridge")))
    from jarvis.modules.stt import _reject_hallucination
    dump = "Alfred, olha o desktop, organiza, cria pasta, pesquisa, toca musica, agenda"
    assert _reject_hallucination(dump) == ""
    assert _reject_hallucination("Thanks for watching") == ""
    keep = _reject_hallucination("Alfred, olha o desktop")
    assert "desktop" in keep.casefold()


def test_inbox_dir_is_under_aura():
    from alfred.tools.engineer import INBOX, ALLOWED_UPLOAD
    assert "aura" in str(INBOX).casefold()
    assert ".zip" in ALLOWED_UPLOAD and ".py" in ALLOWED_UPLOAD and ".png" in ALLOWED_UPLOAD


def test_mic_prefers_realtek():
    from alfred.mic_capture import list_input_devices, pick_device
    devices = list_input_devices()
    assert isinstance(devices, list)
    chosen = pick_device("realtek")
    assert "name" in chosen
    if any("realtek" in d["name"].casefold() for d in devices):
        assert "realtek" in chosen["name"].casefold()


def test_delete_is_dry_without_auth(test_home):
    p = test_home / "Documents" / "x.txt"
    p.write_text("ola", encoding="utf-8")
    r = delete_file({"path": str(p)}, Context("d", authorized=False))
    assert r["dry_run"] is True
    assert p.exists()
    assert str(p) in r["would_delete"][0] or r["would_delete"]


def test_preview_does_not_write(test_home):
    p = test_home / "Documents" / "y.txt"
    p.write_text("v", encoding="utf-8")
    r = preview_change({"path": str(p)}, Context("p", authorized=False))
    assert r["exists"] is True
    assert p.read_text(encoding="utf-8") == "v"


def test_register_worker_rejects_public_ip():
    with pytest.raises(ValidationError):
        _v_reg({"host": "8.8.8.8", "port": 8795})


def test_register_worker_accepts_lan():
    a = _v_reg({"host": "192.168.1.20", "port": 8795})
    assert a["host"] == "192.168.1.20"


def test_protected_ports_never_in_pausable():
    assert PROTECTED_PORTS.isdisjoint(PAUSABLE.keys())
    assert 11434 in PROTECTED_PORTS and 8777 in PROTECTED_PORTS and 8791 in PROTECTED_PORTS


def test_skill_search_finds_local():
    r = search_skill({"query": "hermes operador"}, Context("s", authorized=False))
    assert "local_skills" in r
    assert r["suggested_urls"]


def test_list_apps_shape():
    r = list_apps({}, Context("a", authorized=False))
    names = {x["app"] for x in r["apps"]}
    assert "photoshop" in names and "notepad" in names


def test_router_photoshop_and_focus():
    r = try_handle("Alfred, abre photoshop")
    assert r is not None
    assert r.get("requires_confirmation") is True or r.get("status") in ("planned", "completed", "failed")
    r2 = try_handle("Alfred, modo funcionario")
    assert r2.get("requires_confirmation") is True


def test_nvidia_helper_does_not_crash():
    info = nvidia()
    assert isinstance(info, dict)


def test_games_running_returns_list():
    assert isinstance(games_running(), list)
