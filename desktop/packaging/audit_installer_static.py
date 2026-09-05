from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGING = ROOT / "desktop" / "packaging"
UI_SOURCE = ROOT / "interface" / "aura-quant-x-dashboard" / "client"
UI_DESKTOP = ROOT / "desktop" / "ui" / "matriz_v22"


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label} {detail}")
    return bool(ok)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def main() -> int:
    failures = 0
    files = {
        "iss": PACKAGING / "AURA_Setup.iss",
        "build": PACKAGING / "BUILD_WINDOWS_INSTALLER.ps1",
        "publish": PACKAGING / "PUBLISH_WINDOWS.ps1",
        "manifest": PACKAGING / "installer-manifest.json",
        "wrapper": PACKAGING / "BUILD_WINDOWS_INSTALLER.bat",
        "safe": ROOT / "AURA_ABRIR_DESKTOP_SEGURO.bat",
        "temporary": ROOT / "AURA_INSTALAR_TEMPORARIO_SEGURO.bat",
        "unified": ROOT / "AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat",
        "safe_voice": ROOT / "AURA_RUN_VOICE_SEGURO.bat",
        "automatic": ROOT / "AURA_AUTOMATICO_WINDOWS.ps1",
        "automatic_bat": ROOT / "AURA_AUTOMATICO_WINDOWS.bat",
        "admin": ROOT / "engine" / "admin" / "aura_admin_api.py",
        "admin_core": ROOT / "scripts" / "aura_admin_core.py",
        "engine": ROOT / "engine" / "server.py",
        "bridge": ROOT / "bridge" / "server.py",
        "capture": ROOT / "desktop" / "capture" / "aura-capture.js",
        "browser_host": ROOT / "desktop" / "BrowserHost.cs",
        "program": ROOT / "desktop" / "Program.cs",
        "desktop_config": ROOT / "desktop" / "config" / "desktop.json",
        "main_form": ROOT / "desktop" / "MainForm.cs",
        "supervisor": ROOT / "desktop" / "ServiceSupervisor.cs",
        "voice_server": ROOT / "bridge" / "jarvis_voice_server.py",
        "aura_core": UI_SOURCE / "src" / "lib" / "auraCore.ts",
        "diagnostic_panel": UI_SOURCE / "src" / "components" / "GlobalDiagnosticPanel.tsx",
        "diagnostic_test": ROOT / "interface" / "aura-quant-x-dashboard" / "server" / "auraDiagnosticPanel.test.ts",
        "operator": UI_SOURCE / "src" / "pages" / "OperatorConsole.tsx",
        "tools_panel": UI_SOURCE / "src" / "components" / "ToolsActivationPanel.tsx",
        "pwa_manifest": UI_SOURCE / "public" / "manifest.webmanifest",
        "pwa_sw": UI_SOURCE / "public" / "sw.js",
        "legacy_ui_index": ROOT / "desktop" / "ui" / "index.html",
        "build_info": UI_DESKTOP / "BUILD_INFO.json",
        "inplace": ROOT / "AURA_InPlace.ps1",
        "package_precheck": ROOT / "scripts" / "aura_package_precheck.py",
        "final_check": ROOT / "scripts" / "aura_final_check.py",
        "selftests": ROOT / "scripts" / "run_selftests.py",
        "csproj": ROOT / "desktop" / "Aura.Desktop.csproj",
        "capture_forwarder": ROOT / "desktop" / "CaptureForwarder.cs",
        "deep_diagnostic": ROOT / "engine" / "deep_diagnostic.py",
        "deep_diagnostic_test": ROOT / "tests" / "test_deep_diagnostic.py",
        "wmi": ROOT / "engine" / "pillars" / "external" / "pillar9_wmi_killer.ps1",
    }
    for label, path in files.items():
        failures += not check(f"arquivo {label}", path.is_file(), str(path.relative_to(ROOT)))

    text = {label: read_text(path) for label, path in files.items()}
    try:
        manifest = json.loads(text["manifest"])
    except Exception:
        manifest = {}
    try:
        build_info = json.loads(text["build_info"])
    except Exception:
        build_info = {}
    try:
        pwa_manifest = json.loads(text["pwa_manifest"])
    except Exception:
        pwa_manifest = {}

    failures += not check("ISS usa AppMutex do Desktop", "AppMutex=AURA_QUANTX_V25_DESKTOP_MUTEX" in text["iss"])
    failures += not check("ISS publica somente o EXE do publish", 'Source: "..\\publish\\*"' in text["iss"])
    failures += not check("ISS exclui estado runtime e sessões", all(token in text["iss"] for token in ["engine\\data\\*", "data\\*.duckdb", "data\\*.sqlite*", "data\\*.session", "data\\runtime\\*", "runtime\\*", "*.duckdb", "*.sqlite", "*.session"]))
    failures += not check("ISS não inicia backend ou Ollama", "AURA_INICIAR_SISTEMA.bat" not in text["iss"] and not re.search(r"(?im)^\s*filename:.*(?:ollama|aura_run_bridge|aura_run_engine|aura_run_voice)", text["iss"]))
    failures += not check("manifesto declara paper trade", manifest.get("executionAllowed") is False and manifest.get("backendAutostart") is False)
    failures += not check("manifesto exige WebView2", manifest.get("webView2", {}).get("required") is True)
    failures += not check("manifesto declara payload Operator OS", "desktop/ui/matriz_v22" in text["manifest"] or "desktop/ui" in text["manifest"])
    failures += not check("build é win-x64 autocontido", "Runtime = 'win-x64'" in text["publish"] and "--self-contained" in text["publish"] and "FrameworkDependent" in text["publish"])
    failures += not check("build valida Inno Setup por arquivo/pasta", "Resolve-InnoSetupPath" in text["build"] and "PathType Container" in text["build"] and "PathType Leaf" in text["build"])
    failures += not check("publish valida identidade e hash do EXE", all(token in text["publish"] for token in ["expectedInformationalVersion", "ProductVersion", "Get-FileHash", "AURA_PUBLISH_INFO.json"]))
    failures += not check("publish valida assets locais", "Test-LocalAssetReferences" in text["publish"] and "manifest.webmanifest" in text["publish"] and "sw.js" in text["publish"])
    failures += not check("publish não quebra interpolação PowerShell", "${Label}:" in text["publish"] and "$Label:" not in text["publish"])
    failures += not check("publish ignora rotas dinâmicas API", "^(?:/)?api(?:/|$)" in text["publish"])
    failures += not check("publish não aceita caminho desktop bin", "desktop\\bin" not in text["publish"])
    failures += not check("UI resolve API same-origin no Desktop", all(token in text["aura_core"] for token in ["isNativeAuraHost", "window.location.hostname", "aura.local", "path.startsWith(\"/api/aura/\")"]))
    failures += not check("diagnóstico visual usa payload profundo", all(token in text["diagnostic_panel"] for token in ["loadFullDiagnostic", "linkStateFromDiagnostic", "setLinks(linkStateFromDiagnostic(pack))"]) and "probeAuraLinks()" not in text["diagnostic_panel"])
    failures += not check("regressão impede AUSENTE falso", all(token in text["diagnostic_test"] for token in ["linkStateFromDiagnostic", "engine: ONLINE", "not.toContain(\"AUSENTE\")"]))
    failures += not check("launcher seguro usa publish e manifesto", all(token in text["safe"] for token in ["desktop\\publish\\Aura.QuantX.Desktop.exe", "AURA_PUBLISH_INFO.json", "12.7.0-V25T6-OPERATOR-OS-INDEX-FIX"]) and "desktop\\bin" not in text["safe"])
    failures += not check("launcher seguro não inicia backend", not re.search(r"(?im)^\s*start\s+.*(?:ollama|aura_run_bridge|aura_run_engine|aura_run_voice)", text["safe"]))
    failures += not check("BATs canônicos ASCII CRLF", all(
        path.is_file() and (data := path.read_bytes()) and data.count(b"\r\n") == data.count(b"\n") and all(byte < 128 for byte in data)
        for path in [files["wrapper"], files["safe"], files["temporary"], files["unified"], files["safe_voice"], files["automatic_bat"]]
    ))
    failures += not check("BAT unificado não faz perguntas", "choice " not in text["unified"].lower() and "[S/N]" not in text["unified"] and "[Y/N]" not in text["unified"])
    failures += not check("BAT unificado faz check/copy/publish/log", all(token in text["unified"] for token in ["aura_package_precheck.py", "AURA_INSTALAR_TEMPORARIO_SEGURO.bat", "PUBLISH_WINDOWS.ps1", "aura_final_check.py", "run_selftests.py", "SVC_LOG"]))
    failures += not check("BAT unificado mantém paper trade", all(token in text["unified"] for token in ["PAPER_TRADE=true", "EXECUTION_ALLOWED=false", "GLM_ADVISORY_ONLY=true"]))
    failures += not check("launcher automático é completo e fail-closed", all(token in text["automatic"] for token in ["PUBLISH_WINDOWS.ps1", "RobocopySafe $portable $backup", "Stop-LocalCore", "CreateShortcut", "diagnostics/deep", "PUBLICACAO_WINDOWS=PASS", "EXECUTION_ALLOWED = 'false'", "GLM_ADVISORY_ONLY = 'true'"]))
    failures += not check("launcher automático registra Robocopy e não baixa modelos", all(token in text["automatic"] for token in ["/LOG+:", "robocopy_", "CORNERAI_BRIDGE_REQUIRE_TOKEN"]) and all(token not in text["automatic"].lower() for token in ["pip install", "ollama pull", "curl.exe", "wget.exe"]) and "Start-Process -FilePath $ollama" not in text["automatic"])
    failures += not check("wrapper automático chama PowerShell sem perguntas", "ExecutionPolicy Bypass" in text["automatic_bat"] and "AURA_AUTOMATICO_WINDOWS.ps1" in text["automatic_bat"] and "choice " not in text["automatic_bat"].lower())
    failures += not check("Voice seguro não instala dependência", "pip install" not in text["safe_voice"] and "REPARAR_AURA_VOICE.bat" not in text["safe_voice"])
    failures += not check("Desktop usa mutex nomeado real", "AURA_QUANTX_V25_DESKTOP_MUTEX" in text["program"] and "new Mutex" in text["program"])
    failures += not check("Desktop registra bootstrap e fechamento", all(token in text["program"] for token in ["desktop_process.log", "MUTEX_COLLISION", "FORM_CLOSED", "FATAL_BOOTSTRAP_EXCEPTION", "APPLICATION_RUN_RETURNED"]))
    failures += not check("launcher falha com log quando Desktop fecha", all(token in text["automatic"] for token in ["desktop_process.log", "Desktop encerrou imediatamente"]))
    failures += not check("Desktop serve matriz_v22 e index", 'matriz_v22' in text["browser_host"] and '/index.html' in text["browser_host"] and "SetVirtualHostNameToFolderMapping" in text["browser_host"])
    failures += not check("BrowserHost faz proxy same-origin allowlisted", all(token in text["browser_host"] for token in ["AddWebResourceRequestedFilter", "TryResolveLocalApi", "ForwardLocalApiAsync", "https://", "/api/aura/", "127.0.0.1"]) and "m2.sokkerpro.com" in text["browser_host"])
    failures += not check("BrowserHost invalida cache por revisão e preserva cookies", all(token in text["browser_host"] for token in ["UiCacheRevision", "EnsureFreshUiCacheAsync", "ClearBrowsingDataAsync", "cookies preservados"]))
    failures += not check("fallback legado redireciona para Operator OS", 'matriz_v22/index.html' in text["legacy_ui_index"] and 'window.location.replace' in text["legacy_ui_index"])
    failures += not check("Desktop não registra captura global", "AddScriptToExecuteOnDocumentCreatedAsync" not in text["browser_host"] and "navigation_gated_sokkerpro_only" in text["browser_host"])
    failures += not check("Desktop injeta captura somente em SokkerPRO", "IsSokkerHost" in text["browser_host"] and "InjectAuraCaptureAsync" in text["browser_host"])
    failures += not check("captura tem host-gate antes do timer", "ALLOWED_HOSTS" in text["capture"] and "if (!ALLOWED_HOSTS.has" in text["capture"] and "setInterval" in text["capture"])
    failures += not check("captura não faz POST/fetch direto", "fetch(" not in text["capture"] and "postMessage" in text["capture"] and "AURA_SOKKERPRO_CAPTURE" in text["capture"])
    failures += not check("captura não conhece token ou Bridge", "CORNERAI_BRIDGE_TOKEN" not in text["capture"] and "127.0.0.1:8080" not in text["capture"])
    failures += not check("Bridge exige token por padrão", all(token in text["bridge"] for token in ["_REQUIRE_BRIDGE_TOKEN", "X-CornerAI-Token", "not _BRIDGE_TOKEN", "_json(503"]))
    failures += not check("Bridge CORS é allowlist exata", all(token in text["bridge"] for token in ["https://aura.local", "https://m2.sokkerpro.com"]) and ".endswith(\".sokkerpro.com\")" not in text["bridge"] and "chrome-extension://" not in text["bridge"])
    failures += not check("Engine não expõe porta legada 8766", "8766" not in text["desktop_config"] and "8766" not in text["engine"])
    failures += not check("Engine CORS é estreito", "AURA_ENGINE_ORIGIN_REGEX" in text["engine"] and "(3000|8080|8099|8765)" not in text["engine"] and "8766" not in text["engine"])
    failures += not check("Admin API tem auth global e approver separado", all(token in text["admin"] for token in ["dependencies=[Depends(_require_admin_auth)]", "_require_approver_auth", "AURA_ADMIN_APPROVER_TOKEN", "AURA_ADMIN_APPROVER_ID"]))
    failures += not check("Admin API impõe teto de modo", all(token in text["admin"] for token in ["_enforce_mode_ceiling", "_GATE.set_mode_ceiling", "MODE_CEILING_BLOCKED"]))
    failures += not check("Admin API consome grants atomicamente", "consume_many" in text["admin"] and "grant_consume_failed" in text["admin"])
    failures += not check("PolicyGate suporta teto configurado", "set_mode_ceiling" in text["admin_core"] and "autonomy mode exceeds configured ceiling" in text["admin_core"])
    failures += not check("mutações do Engine exigem token dedicado", all(token in text["engine"] for token in ["AURA_MUTATION_TOKEN", "_mutation_auth_error", "/api/tools/activate-all", "/api/feedback", "mutation_token_not_configured"]))
    failures += not check("UI não chama ativação mutante", "activateAllTools" not in text["tools_panel"] and "installAndActivateMax" not in text["tools_panel"] and "ATIVAÇÃO ADMIN" in text["tools_panel"])
    failures += not check("UI não envia feedback sem canal admin", "postFeedback" not in text["operator"] and "Feedback protegido" in text["operator"])
    failures += not check("PWA usa entrada canônica", pwa_manifest.get("start_url") == "/index.html" and pwa_manifest.get("scope") == "/" and "/manus-storage/" not in text["pwa_manifest"])
    failures += not check("service worker define cache e entry", "const CACHE_NAME" in text["pwa_sw"] and "entryUrl" in text["pwa_sw"] and "event.request.mode === \"navigate\"" in text["pwa_sw"])
    all_ui_text = "\n".join(read_text(path) for path in UI_SOURCE.rglob("*.*") if path.is_file() and "node_modules" not in path.parts and path.suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".css"})
    failures += not check("frontend não usa manus-storage", "manus-storage" not in all_ui_text)
    failures += not check("frontend não usa analytics externo", all(token not in all_ui_text for token in ["VITE_ANALYTICS", "fonts.googleapis.com", "umami"]))
    failures += not check("BUILD_INFO identifica release", build_info.get("build_id") == "12.7.0-V25T6-OPERATOR-OS-INDEX-FIX" and build_info.get("hosted_under") == "/index.html" and build_info.get("security_release") == "V25T6-SECURITY-HARDENED" and build_info.get("fallback") is None)
    failures += not check("bundle Desktop não tem instrumentação __manus__", not (UI_DESKTOP / "__manus__").exists())
    failures += not check("bundle Desktop tem index/manifest/sw", all((UI_DESKTOP / item).is_file() for item in ["index.html", "manifest.webmanifest", "sw.js", "BUILD_INFO.json"]))
    failures += not check("bundle Desktop resolve assets do index", all((UI_DESKTOP / ref).is_file() for ref in re.findall(r'(?:src|href)=["\'](?:\./)?([^"\']+)["\']', read_text(UI_DESKTOP / "index.html")) if not ref.startswith(("http:", "https:", "data:"))))
    failures += not check("AURA_InPlace registra lock e retenção", all(token in text["inplace"] for token in ["started_at", "Test-ProcessAlive", "LockStaleAfterSeconds", "Prune-Backups", "BackupRetention"]))
    failures += not check("WMI não sobrescreve PID automático", "$processId" in text["wmi"] and "$pid =" not in text["wmi"] and "$pid:" not in text["wmi"])
    failures += not check("CaptureForwarder sem nulabilidade conhecida", "Func<string, Task<bool>>? send" in text["capture_forwarder"] and "string? item" in text["capture_forwarder"])
    failures += not check("diagnóstico não sonda Engine recursivamente", "self_liveness" in text["deep_diagnostic"] and "engine_request_liveness" in text["deep_diagnostic"] and "collect_diagnostic, self_liveness=True" in text["engine"])
    failures += not check("regressão do diagnóstico presente", files["deep_diagnostic_test"].is_file())
    failures += not check("AURA_InPlace só inicia Ollama por opt-in", "StartOllama" in text["inplace"] and "if ($StartOllama)" in text["inplace"] and "Ensure-Ollama" in text["inplace"])
    failures += not check("pré-check e final check existem", files["package_precheck"].is_file() and files["final_check"].is_file() and files["selftests"].is_file())

    if failures:
        print(f"INSTALLER_STATIC_AUDIT=FAIL failures={failures}")
        return 1
    print("INSTALLER_STATIC_AUDIT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
