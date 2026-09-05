from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_config() -> None:
    config = json.loads((ROOT / "desktop/config/desktop.json").read_text(encoding="utf-8"))
    assert config["app"]["paperTradeOnly"] is True
    assert config["security"]["allowRealOrders"] is False
    assert config["app"]["virtualHost"] == "aura.local"
    services = {item["name"]: item for item in config["services"]}
    assert [services[name]["port"] for name in ("Bridge", "Engine", "Voice")] == [8080, 8765, 8099]
    assert config["ollama"]["model"] == "glm4:9b-chat-q4_0"


def test_agent_catalog_matches_manifest() -> None:
    manifest = json.loads((ROOT / "agents/activation_manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((ROOT / "desktop/ui/agents.json").read_text(encoding="utf-8"))
    assert catalog["paperTradeOnly"] is True
    assert catalog["agentCount"] == manifest["agent_count"] == 34
    assert len(catalog["agents"]) == 34
    assert {item["id"] for item in catalog["agents"]} == set(manifest["agents"])


def test_capture_is_extension_free_and_fail_closed() -> None:
    capture = (ROOT / "desktop/capture/aura-capture.js").read_text(encoding="utf-8")
    assert not any(token in capture for token in ("chrome.runtime.sendMessage", "chrome.runtime.onMessage", "chrome.runtime.getURL"))
    assert "AURA_SOKKERPRO_CAPTURE" in capture
    assert "cornerai-analyst-1" in capture
    assert "pressure:" in capture
    assert "corners: { total:" in capture
    assert "window.chrome.webview.postMessage" in capture
    assert "null" in capture


def test_python_syntax() -> None:
    for path in (ROOT / "desktop/update_manual.py", ROOT / "desktop/tools/build_agent_catalog.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_capture_bridge_normalization() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    from bridge.server import extract_match_view, validate_skill_pack, view_to_skill_pack

    payload = {
        "schema": "cornerai-analyst-1",
        "fixture": {"id": "123456", "home": "Casa", "away": "Fora", "minute": 34, "score": [1, 0], "status": "live"},
        "pressure": {"attacks": [20, 16], "dangerous": [8, 5], "shotsOn": [3, 2], "possession": [54, 46], "xg": [0.8, 0.4]},
        "corners": {"total": [4, 2], "events": [{"minute": 31, "team": "home"}]},
    }
    view = extract_match_view(payload)
    assert view["fixture_id"] == "123456"
    assert view["corners_home"] == 4 and view["corners_away"] == 2
    pack = view_to_skill_pack(view, payload)
    assert validate_skill_pack(pack) == []


def test_desktop_csharp_contract() -> None:
    project = (ROOT / "desktop/Aura.Desktop.csproj").read_text(encoding="utf-8")
    browser = (ROOT / "desktop/BrowserHost.cs").read_text(encoding="utf-8")
    supervisor = (ROOT / "desktop/ServiceSupervisor.cs").read_text(encoding="utf-8")
    form = (ROOT / "desktop/MainForm.cs").read_text(encoding="utf-8")
    assert "net8.0-windows" in project and "Microsoft.Web.WebView2" in project and "PlatformTarget>x64" in project
    assert "SetVirtualHostNameToFolderMapping" in browser
    assert "AddScriptToExecuteOnDocumentCreatedAsync" in browser
    assert "AURA_SOKKERPRO_CAPTURE" in browser and "IsSokkerHost" in browser
    assert "StartAllAsync" in supervisor and "CheckHealthAsync" in supervisor
    assert ".Kill(" not in supervisor and ".Kill(" not in form
    config = json.loads((ROOT / "desktop/config/desktop.json").read_text(encoding="utf-8"))
    assert "/api/cornerai/feed" in form and config["security"]["allowRealOrders"] is False


def test_required_desktop_files() -> None:
    for relative in (
        "desktop/Aura.Desktop.csproj",
        "desktop/Program.cs",
        "desktop/MainForm.cs",
        "desktop/BrowserHost.cs",
        "desktop/ServiceSupervisor.cs",
        "desktop/app.manifest",
        "desktop/ui/index.html",
        "desktop/ui/app.js",
        "desktop/ui/styles.css",
        "desktop/README.md",
        "desktop/ARCHITECTURE.md",
        "desktop/packaging/EXE_PREPARATION.md",
        "MANUAL_SISTEMA_AURA.txt",
    ):
        assert (ROOT / relative).is_file(), relative


def test_matrix_and_first_start_contract() -> None:
    config = json.loads((ROOT / "desktop/config/desktop.json").read_text(encoding="utf-8"))
    assert config["app"]["homepage"].endswith("/matriz/aura-quantx-central.html")
    manifest = json.loads((ROOT / "agents/activation_manifest.json").read_text(encoding="utf-8"))
    assert manifest["agent_count"] == 34 and len(manifest["agents"]) == 34
    assert len(manifest["tools"]) == 13
    for relative in (
        "desktop/ui/matriz/aura-quantx-central.html",
        "desktop/ui/matriz/aura-quantx-central.css",
        "desktop/ui/matriz/aura-quantx-central.js",
        "desktop/ui/matriz/aura-quantx-adapter.js",
        "scripts/aura_install_activation_check.py",
    ):
        assert (ROOT / relative).is_file(), relative
    adapter = (ROOT / "desktop/ui/matriz/aura-quantx-adapter.js").read_text(encoding="utf-8")
    form = (ROOT / "desktop/MainForm.cs").read_text(encoding="utf-8")
    assert "/api/glm_chat" in adapter and "getActivation" in adapter
    assert "EnsureOllamaAsync" in form


def test_inplace_guards_and_preservation_contract() -> None:
    allowlist = json.loads((ROOT / "allowlist.json").read_text(encoding="utf-8"))
    assert allowlist["schema"] == "aura-inplace-allowlist-v1"
    assert "engine/venv/**" in allowlist["protected"]
    assert "**/*.db" in allowlist["protected"]
    assert allowlist["policy"]["allowOllamaPull"] is False
    updater = (ROOT / "AURA_InPlace.ps1").read_text(encoding="utf-8").lower()
    launcher = (ROOT / "AURA_REPARAR_SISTEMA.bat").read_bytes()
    assert "test-protectedpath" in updater and "invoke-rollbackinternal" in updater
    assert b"\r\n" in launcher
    assert "execution_allowed" in updater and "paper" in updater
