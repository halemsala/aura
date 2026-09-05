"""AURA QUANT-X — pré-check somente leitura do pacote.

Valida estrutura, payload Operator OS, sintaxe Python, BATs canônicos,
contrato do Bridge e invariantes paper-trade. Não modifica arquivos,
não inicia serviços e não instala dependências.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

# Blindagem de encoding: stdout/stderr redirecionado para arquivo de log
# pode herdar cp1252 do console Windows em vez de UTF-8, derrubando print()
# com UnicodeEncodeError. Reconfigura com fallback seguro.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(os.environ.get("AURA_PACKAGE_ROOT") or os.environ.get("AURA_SELF_TEST_ROOT") or Path(__file__).resolve().parents[1]).resolve()
ERRORS: list[str] = []
WARNINGS: list[str] = []


def ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  [AVISO] {msg}")


def fail(msg: str) -> None:
    ERRORS.append(msg)
    print(f"  [ERRO]  {msg}")


CRITICAL_FILES = (
    "engine/server.py",
    "engine/agent_glm_runtime.py",
    "engine/core/security.py",
    "bridge/server.py",
    "desktop/Aura.Desktop.csproj",
    "desktop/config/desktop.json",
    "desktop/capture/aura-capture.js",
    "desktop/ui/matriz_v22/index.html",
    "desktop/ui/matriz_v22/BUILD_INFO.json",
    "desktop/ui/matriz_v22/manifest.webmanifest",
    "desktop/ui/matriz_v22/sw.js",
    "desktop/packaging/PUBLISH_WINDOWS.ps1",
    "desktop/packaging/AURA_Setup.iss",
    "AURA_ABRIR_DESKTOP_SEGURO.bat",
    "AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat",
    "AURA_INSTALAR_TEMPORARIO_SEGURO.bat",
    "AURA_RUN_VOICE_SEGURO.bat",
    "scripts/aura_final_check.py",
    "scripts/run_selftests.py",
    "scripts/aura_package_precheck.py",
    "engine/aura_ai_one/__init__.py",
    "engine/aura_ai_one/contracts.py",
    "engine/aura_ai_one/features.py",
    "engine/aura_ai_one/adapter.py",
    "engine/agents/aura_hermes_router.py",
    "engine/aura_controller.py",
    "engine/core/runtime_manifest.py",
    "engine/agents/llm_firewall.py",
    "config/config.root.json",
    "config/aura_sports_corner_profile.json",
)

CRITICAL_SYNTAX = (
    "engine/aura_ai_one/contracts.py",
    "engine/aura_ai_one/features.py",
    "engine/aura_ai_one/adapter.py",
    "engine/agents/aura_hermes_router.py",
    "engine/aura_controller.py",
    "engine/core/runtime_manifest.py",
    "engine/agents/llm_firewall.py",
    "engine/server.py",
    "bridge/server.py",
    "engine/agents/natural_voice.py",
    "engine/agents/tipster_capture.py",
    "engine/agents/intent_router.py",
    "scripts/aura_final_check.py",
    "scripts/run_selftests.py",
    "scripts/aura_package_precheck.py",
)

CRITICAL_BATS = (
    "AURA_ABRIR_DESKTOP_SEGURO.bat",
    "AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat",
    "AURA_INSTALAR_TEMPORARIO_SEGURO.bat",
    "AURA_RUN_VOICE_SEGURO.bat",
)


def check_structure() -> None:
    print("\n[1/8] Estrutura de pastas")
    for directory in ("engine", "engine/aura_ai_one", "bridge", "scripts", "desktop", "desktop/ui/matriz_v22", "desktop/packaging"):
        if (ROOT / directory).is_dir():
            ok(f"pasta {directory}/")
        else:
            fail(f"pasta ausente: {directory}/")


def check_files() -> None:
    print("\n[2/7] Ficheiros canônicos")
    for relative in CRITICAL_FILES:
        if (ROOT / relative).is_file():
            ok(relative)
        else:
            fail(f"ausente: {relative}")


def check_operator_os() -> None:
    print("\n[3/7] Operator OS e publicação")
    build_info_path = ROOT / "desktop/ui/matriz_v22/BUILD_INFO.json"
    manifest_path = ROOT / "desktop/ui/matriz_v22/manifest.webmanifest"
    index_path = ROOT / "desktop/ui/matriz_v22/index.html"
    try:
        build = json.loads(build_info_path.read_text(encoding="utf-8"))
        expected = {
            "build_id": "12.7.0-V25T6-OPERATOR-OS-INDEX-FIX",
            "hosted_under": "/index.html",
            "security_release": "V25T6-SECURITY-HARDENED",
        }
        for key, value in expected.items():
            if build.get(key) == value:
                ok(f"BUILD_INFO {key}={value}")
            else:
                fail(f"BUILD_INFO inválido: {key}={build.get(key)!r}")
    except Exception as exc:
        fail(f"BUILD_INFO ilegível: {exc}")
    try:
        pwa = json.loads(manifest_path.read_text(encoding="utf-8"))
        if pwa.get("start_url") == "/index.html" and pwa.get("scope") == "/":
            ok("PWA aponta para /index.html")
        else:
            fail("PWA não usa start_url=/index.html e scope=/")
    except Exception as exc:
        fail(f"manifest.webmanifest ilegível: {exc}")
    index = index_path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"manus-storage|umami|VITE_ANALYTICS|fonts\.googleapis", index):
        fail("index.html contém asset/analytics externo proibido")
    else:
        ok("index.html sem referências externas proibidas")
    publish_info = ROOT / "desktop/publish/AURA_PUBLISH_INFO.json"
    if publish_info.is_file():
        try:
            record = json.loads(publish_info.read_text(encoding="utf-8"))
            if record.get("build_id") == "12.7.0-V25T6-OPERATOR-OS-INDEX-FIX" and record.get("sha256"):
                ok("AURA_PUBLISH_INFO.json identifica o EXE publicado")
            else:
                fail("AURA_PUBLISH_INFO.json não corresponde à build esperada")
        except Exception as exc:
            fail(f"AURA_PUBLISH_INFO.json ilegível: {exc}")
    else:
        warn("EXE ainda não publicado; o publish Windows será validado na etapa própria")


def check_syntax() -> None:
    print("\n[4/7] Sintaxe Python")
    for relative in CRITICAL_SYNTAX:
        path = ROOT / relative
        if not path.is_file():
            fail(f"ausente para sintaxe: {relative}")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            ok(f"sintaxe {relative}")
        except SyntaxError as exc:
            fail(f"sintaxe {relative}: linha {exc.lineno}: {exc.msg}")
        except Exception as exc:
            fail(f"leitura {relative}: {exc}")


def check_bats() -> None:
    print("\n[5/7] Launchers BAT canônicos")
    for relative in CRITICAL_BATS:
        path = ROOT / relative
        if not path.is_file():
            fail(f"ausente: {relative}")
            continue
        raw = path.read_bytes()
        if len(raw) < 40:
            fail(f"demasiado pequeno: {relative}")
            continue
        if any(byte >= 128 for byte in raw):
            fail(f"não ASCII: {relative}")
        if b"\n" in raw.replace(b"\r\n", b"") or b"\r" in raw.replace(b"\r\n", b""):
            fail(f"terminador não CRLF: {relative}")
        else:
            ok(f"{relative} ({len(raw)} bytes, ASCII CRLF)")


def check_bridge_contract() -> None:
    print("\n[6/7] Contrato Bridge e segurança")
    path = ROOT / "bridge/server.py"
    source = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"def\s+do_GET\s*\(", source) and "/health" in source:
        ok("Bridge possui health GET")
    else:
        fail("Bridge não expõe contrato health GET")
    if "_REQUIRE_BRIDGE_TOKEN" in source and "X-CornerAI-Token" in source and "_json(503" in source:
        ok("Bridge exige token e falha fechado sem provisionamento")
    else:
        fail("Bridge não confirma autenticação fail-closed")
    if "fetch(" not in (ROOT / "desktop/capture/aura-capture.js").read_text(encoding="utf-8", errors="replace"):
        ok("captura não faz fetch direto ao Bridge")
    else:
        fail("captura ainda faz fetch direto ao Bridge")


def check_ai_integration() -> None:
    print("\n[7/8] AURA IA One + Hermes")
    symbols = {
        "engine/aura_ai_one/adapter.py": ("AuraAIOneAdapter", "HermesAuditAdapter"),
        "engine/agents/aura_hermes_router.py": ("aura-hermes-envelope-v1", "AURA_AI_ONE_QUANT", "HERMES_AUDIT"),
        "engine/aura_controller.py": ("evaluate_corners", "AuditLedger"),
    }
    for relative, required in symbols.items():
        path = ROOT / relative
        source = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        missing = [token for token in required if token not in source]
        if missing:
            fail(f"integração incompleta em {relative}: ausente {missing}")
        else:
            ok(f"símbolos de integração presentes em {relative}")
    config_path = ROOT / "config/config.root.json"
    profile_path = ROOT / "config/aura_sports_corner_profile.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        orchestration = config.get("ai_orchestration", {})
        expected = {
            "contract": "aura-hermes-advisory-v1",
            "order": ["AURA_AI_ONE_QUANT", "HERMES_AUDIT"],
            "network_default": False,
            "tool_authority": False,
        }
        for key, value in expected.items():
            if orchestration.get(key) == value:
                ok(f"configuração ai_orchestration {key} válida")
            else:
                fail(f"configuração ai_orchestration inválida: {key}={orchestration.get(key)!r}")
    except Exception as exc:
        fail(f"configuração raiz de IA ilegível: {exc}")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if profile.get("profile_id") == "aura-corners-pro-v1" and profile.get("financial_operations_enabled") is False:
            ok("perfil aura-corners-pro-v1 sem operações financeiras")
        else:
            fail("perfil de escanteios inválido ou financeiro")
    except Exception as exc:
        fail(f"perfil de escanteios ilegível: {exc}")


def check_policy() -> None:
    print("\n[8/8] Política paper_trade / execution")
    breaches = []
    for path in (ROOT / "engine").rglob("*.py"):
        relative_parts = path.relative_to(ROOT).parts
        if "tests" in relative_parts or path.name.startswith("test_"):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if re.search(r"^\s*execution_allowed\s*=\s*True\s*(?:#.*)?$", source, re.MULTILINE):
            breaches.append(str(path.relative_to(ROOT)))
    if breaches:
        for breach in breaches[:10]:
            fail(f"execution_allowed=True em {breach}")
    else:
        ok("nenhum execution_allowed=True no código de produção do engine/")
    security = ROOT / "engine/core/security.py"
    source = security.read_text(encoding="utf-8", errors="ignore") if security.is_file() else ""
    if all(token in source for token in ["PAPER_TRADE", "EXECUTION_ALLOWED", "GLM_ADVISORY_ONLY"]):
        ok("invariantes de segurança presentes")
    else:
        fail("invariantes de segurança incompletos")


def main() -> int:
    print("=" * 72)
    print(" AURA QUANT-X — PRE-CHECK DO PACOTE OPERATOR OS V25T6")
    print(f" ROOT: {ROOT}")
    print("=" * 72)
    if not ROOT.is_dir():
        print(f"[ERRO] ROOT inválido: {ROOT}")
        return 1
    check_structure()
    check_files()
    check_operator_os()
    check_syntax()
    check_bats()
    check_bridge_contract()
    check_ai_integration()
    check_policy()
    print("\n" + "=" * 72)
    print(f" RESULTADO: {len(ERRORS)} erro(s), {len(WARNINGS)} aviso(s)")
    print("=" * 72)
    if ERRORS:
        for error in ERRORS:
            print(f"  - {error}")
        print("\nCorrija os erros antes de instalar/iniciar.")
        return 1
    print("\nPacote pronto para a etapa seguinte; nenhum serviço foi iniciado.")
    if WARNINGS:
        print("(Avisos não bloqueiam, mas devem ser revistos.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
