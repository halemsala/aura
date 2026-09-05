#!/usr/bin/env python3
"""Autoteste bloqueante e pós-instalação do AURA QUANT-X.

Fases:
  pre   - executada com o Python do sistema antes da instalação;
  post  - executada com engine\\venv\\Scripts\\python.exe após dependências;
  final - executada após subir os três serviços.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

EXPECTED_PACKAGE_PREFIX = "AURA-QUANT-X-12.7.0-"
EXPECTED_VOICE_BUILD = "AURA-VOICE-MALE-V3"
EXPECTED_MODEL = "glm4:9b-chat-q4_0"
REQUIRED_FILES = (
    "AURA_INSTALAR_E_INICIAR_TUDO.bat",
    "AURA_REPARAR_SISTEMA.bat",
    "AURA_InPlace.ps1",
    "allowlist.json",
    "scripts/aura_install_activation_check.py",
    "scripts/test_in_place_update.py",
    "desktop/ui/matriz/aura-quantx-central.html",
    "desktop/ui/matriz/aura-quantx-central.css",
    "desktop/ui/matriz/aura-quantx-central.js",
    "desktop/ui/matriz/aura-quantx-adapter.js",
    "desktop/ui/matriz_v22/index.html",
    "desktop/ui/matriz_v22/manifest.webmanifest",
    "desktop/ui/matriz_v22/sw.js",
    "engine/knowledge_review_gate.py",
    "knowledge/inbox/knowledge_candidates.jsonl",
    "knowledge/approved/knowledge.jsonl",
    "knowledge/review_decisions.jsonl",
    "ARQUIVO_LEGADO/BAT_PS1/INSTALAR_AURA_12_7_0_FINAL.bat",
    "ARQUIVO_LEGADO/BAT_PS1/AURA_RUN_BRIDGE.bat",
    "ARQUIVO_LEGADO/BAT_PS1/AURA_RUN_ENGINE.bat",
    "ARQUIVO_LEGADO/BAT_PS1/AURA_RUN_VOICE.bat",
    "bridge/server.py",
    "bridge/jarvis_voice_server.py",
    "bridge/voice_preflight.py",
    "bridge/requirements_voice.txt",
    "bridge/jarvis/config.yaml",
    "engine/server.py",
    "requirements.txt",
    "voice_assets/voz_masculina_referencia.wav",
    "voice_assets/PROMPT_GROK_VOZ.md",
    "voice_assets/PERFIL_ESTILO_ESPORTIVO.md",
)
CRITICAL_PYTHON = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "numpy",
    "requests",
    "yaml",
    "zmq",
    "faster_whisper",
    "ctranslate2",
    "sounddevice",
    "edge_tts",
)
CRITICAL_SOURCE = (
    "bridge/jarvis_voice_server.py",
    "bridge/voice_preflight.py",
    "bridge/jarvis/modules/neural_tts.py",
    "desktop/update_manual.py",
)
PORTS = {"Bridge": 8080, "Engine": 8765, "Voice": 8099}


def add(checks: list[dict[str, Any]], name: str, ok: bool, detail: str, *, warning: bool = False) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail, "warning": bool(warning)})


def find_ollama() -> Path | None:
    candidates = [
        shutil.which("ollama.exe"),
        shutil.which("ollama"),
    ]
    local = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    candidates.append(str(local))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def run_process(args: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def endpoint(url: str, timeout: int = 4) -> tuple[bool, dict[str, Any] | str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return response.status == 200, json.loads(raw)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except OSError:
        return False


def validate_bat_line_endings(root: Path, checks: list[dict[str, Any]]) -> None:
    bats = sorted(root.rglob("*.bat"))
    if not bats:
        add(checks, "BATs encontrados", False, "nenhum BAT encontrado")
        return
    bad: list[str] = []
    for path in bats:
        raw = path.read_bytes()
        if bytes([13, 10]) not in raw or bytes([10]) in raw.replace(bytes([13, 10]), b""):
            bad.append(str(path.relative_to(root)))
    add(checks, "BATs em CRLF", not bad, ", ".join(bad) if bad else f"{len(bats)} BATs em CRLF")


def common_checks(root: Path, checks: list[dict[str, Any]], *, check_ports: bool) -> None:
    marker = root / "PACKAGE_RELEASE.txt"
    marker_value = marker.read_text(encoding="utf-8-sig").strip() if marker.is_file() else ""
    marker_ok = marker_value.startswith(EXPECTED_PACKAGE_PREFIX)
    add(checks, "Marcador do pacote", marker_ok, marker_value or "ausente")
    missing = [rel for rel in REQUIRED_FILES if not (root / rel).is_file()]
    add(checks, "Estrutura obrigatória", not missing, ", ".join(missing) if missing else "arquivos principais presentes")
    matrix_dir = root / "desktop" / "ui" / "matriz_v22"
    matrix_js = sorted(matrix_dir.glob("assets/*.js")) if matrix_dir.is_dir() else []
    matrix_css = sorted(matrix_dir.glob("assets/*.css")) if matrix_dir.is_dir() else []
    add(checks, "Assets compilados Matriz V22", bool(matrix_js and matrix_css), f"js={len(matrix_js)}; css={len(matrix_css)}")
    root_bats = sorted(path.name for path in root.glob("*.bat"))
    allowed_root_bats = {
        "AURA_INSTALAR_E_INICIAR_TUDO.bat",
        "AURA_REPARAR_SISTEMA.bat",
        "AURA_INICIAR_SISTEMA.bat",
        "AURA_PRECHECK_PACOTE.bat",
        "AURA_TUDO_EM_UM.bat",
        "AURA_EMPACOTAR_RELEASE.bat",
        "AURA_ATIVAR_VOZ_REFERENCIA.bat",
        "AURA_RESTAURAR_VOZ_EDGE.bat",
        # V25T / V25E oficiais adicionais (Desktop / Matriz / utilitarios / diagnostico)
        "ABRIR_DESKTOP.bat",
        "ABRIR_INTERFACE.bat",
        "APLICAR_PATCH.bat",
        "AURA_ABRIR_DESKTOP_SEGURO.bat",
        "AURA_ABRIR_E_VER.bat",
        "AURA_ABRIR_MATRIZ.bat",
        "AURA_ATIVAR_TUDO.bat",
        "AURA_AUTOMATICO_WINDOWS.bat",
        "AURA_COMPILAR_DESKTOP.bat",
        "AURA_CRIAR_VENV.bat",
        "AURA_DIAGNOSTICO_COMPLETO.bat",
        "AURA_INICIAR_SERVICOS_EMERGENCIA.bat",
        "AURA_INICIAR_TUDO_DESKTOP.bat",
        "AURA_INSTALAR_CHECK_INICIAR_SEGURO.bat",
        "AURA_INSTALAR_TEMPORARIO_SEGURO.bat",
        "AURA_RUN_VOICE_SEGURO.bat",
        "AURA_UI_SERVER.bat",
    }
    # Exige instalador + entrada unica; permite apenas BATs da whitelist
    required_root = {"AURA_INSTALAR_E_INICIAR_TUDO.bat", "AURA_TUDO_EM_UM.bat"}
    root_bats_ok = required_root.issubset(set(root_bats)) and set(root_bats).issubset(allowed_root_bats)
    add(checks, "BATs oficiais na raiz", root_bats_ok, ", ".join(root_bats) or "nenhum")
    validate_bat_line_endings(root, checks)
    add(checks, "Python mínimo", sys.version_info >= (3, 10), platform.python_version())
    add(checks, "Arquitetura", platform.machine().lower() in {"amd64", "x86_64", "x64"}, platform.machine())
    free_gb = shutil.disk_usage(root).free / (1024**3)
    add(checks, "Espaço livre", free_gb >= 8, f"{free_gb:.1f} GB livres", warning=free_gb < 12)
    for name, port in PORTS.items():
        occupied = port_is_open(port)
        add(checks, f"Porta {port} livre antes da instalação", not occupied, f"{name}: {'ocupada' if occupied else 'livre'}")
    ollama = find_ollama()
    if ollama is None:
        add(checks, "Ollama", False, "ollama.exe não encontrado")
    else:
        code, output = run_process([str(ollama), "--version"], timeout=20)
        add(checks, "Ollama executável", code == 0, output[-240:] or str(ollama))
        code, output = run_process([str(ollama), "list"], timeout=30)
        model_present = code == 0 and EXPECTED_MODEL.lower() in output.lower()
        add(checks, "Modelo GLM-4", True, "presente" if model_present else "ausente; será baixado pelo instalador", warning=not model_present)
    source_text = "\n".join((root / rel).read_text(encoding="utf-8", errors="replace") for rel in CRITICAL_SOURCE if (root / rel).is_file())
    add(checks, "PAPER TRADE", "PAPER" in source_text.upper() and "REAL" in source_text.upper(), "marcadores de segurança encontrados")
    candidate_path = root / "knowledge" / "inbox" / "knowledge_candidates.jsonl"
    approved_path = root / "knowledge" / "approved" / "knowledge.jsonl"
    decision_path = root / "knowledge" / "review_decisions.jsonl"
    candidate_count = sum(1 for line in candidate_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()) if candidate_path.is_file() else 0
    approved_count = sum(1 for line in approved_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()) if approved_path.is_file() else 0
    add(checks, "Corpus candidato presente", True, f"{candidate_count} candidatos pendentes", warning=candidate_count == 0)
    add(checks, "Memória aprovada vazia por padrão", approved_count == 0, f"{approved_count} itens aprovados")
    add(checks, "Ledger de decisões presente", decision_path.is_file(), str(decision_path))


def pre_phase(root: Path) -> int:
    checks: list[dict[str, Any]] = []
    common_checks(root, checks, check_ports=True)
    report(checks, "AURA_SELF_TEST_PRE")
    return finish(checks)


def post_phase(root: Path) -> int:
    checks: list[dict[str, Any]] = []
    expected_python = root / "engine" / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    executable = Path(sys.executable).resolve()
    add(checks, "Python da venv", executable == expected_python.resolve() if expected_python.exists() else False, str(executable))
    missing: list[str] = []
    versions: dict[str, str] = {}
    for name in CRITICAL_PYTHON:
        try:
            module = importlib.import_module(name)
            versions[name] = str(getattr(module, "__version__", "ok"))
        except Exception as exc:
            missing.append(f"{name}: {exc}")
    add(checks, "Imports críticos", not missing, "; ".join(missing) if missing else ", ".join(f"{k}={v}" for k, v in versions.items()))
    for rel in CRITICAL_SOURCE:
        path = root / rel
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            ok = True
            detail = "AST válido"
        except Exception as exc:
            ok = False
            detail = str(exc)
        add(checks, f"Sintaxe {rel}", ok, detail)
    config = (root / "bridge/jarvis/config.yaml").read_text(encoding="utf-8", errors="replace")
    add(checks, "Voz configurada", 'voice_name: "pt-BR-AntonioNeural"' in config, "pt-BR-AntonioNeural esperado")
    add(checks, "XTTS não forçado", "xtts_enabled: false" in config, "xtts_enabled=false esperado")
    neural = (root / "bridge/jarvis/modules/neural_tts.py").read_text(encoding="utf-8", errors="replace")
    add(checks, "Política masculina", "_APPROVED_MALE_VOICES" in neural and "VOICE_SELECTION_ERROR" in neural and "Francisca" not in neural, "allowlist masculina e sem fallback feminino")
    report(checks, "AURA_SELF_TEST_POST")
    return finish(checks)


def final_phase(root: Path, wait_seconds: int) -> int:
    deadline = time.monotonic() + max(1, wait_seconds)
    last: list[dict[str, Any]] = []
    while time.monotonic() <= deadline:
        checks: list[dict[str, Any]] = []
        bridge_ok, bridge = endpoint("http://127.0.0.1:8080/health")
        engine_ok, engine = endpoint("http://127.0.0.1:8765/api/status")
        voice_ok, voice = endpoint("http://127.0.0.1:8099/api/voice/health")
        diag_ok, diag = endpoint("http://127.0.0.1:8099/api/voice/diagnostic")
        add(checks, "Bridge health", bridge_ok, str(bridge)[:240])
        add(checks, "Engine status", engine_ok, str(engine)[:240])
        build = voice.get("build_id") if isinstance(voice, dict) else None
        add(checks, "Voice health/build", voice_ok and build == EXPECTED_VOICE_BUILD, f"build_id={build}")
        voice_profile = diag.get("voiceProfile") if isinstance(diag, dict) else None
        voice_runtime = diag.get("voiceRuntime") if isinstance(diag, dict) else None
        configured = voice_profile.get("configured_voice") if isinstance(voice_profile, dict) else None
        gender = voice_runtime.get("gender") if isinstance(voice_runtime, dict) else None
        add(checks, "Voice diagnóstico", diag_ok and isinstance(diag, dict) and diag.get("build_id") == EXPECTED_VOICE_BUILD, f"build_id={diag.get('build_id') if isinstance(diag, dict) else None}")
        add(checks, "Voz masculina efetiva", configured == "pt-BR-AntonioNeural" and gender == "male", f"voice={configured}; gender={gender}")
        ollama_ok, ollama = endpoint("http://127.0.0.1:11434/api/tags")
        models = ollama.get("models", []) if isinstance(ollama, dict) else []
        model_names = [str(item.get("name", "")) for item in models if isinstance(item, dict)]
        add(checks, "Ollama e GLM", ollama_ok and EXPECTED_MODEL in model_names, f"modelos={model_names}")
        catalog_ok, catalog = endpoint("http://127.0.0.1:8765/api/agents")
        agent_count = catalog.get("count") if isinstance(catalog, dict) else None
        declared_count = catalog.get("declaredCount") if isinstance(catalog, dict) else None
        add(checks, "Catálogo completo de agentes", catalog_ok and isinstance(agent_count, int) and agent_count == declared_count and agent_count >= 30, f"count={agent_count}; declaredCount={declared_count}")
        glm_ok, glm_status = endpoint("http://127.0.0.1:8765/api/agents/glm/status")
        glm_active = isinstance(glm_status, dict) and glm_status.get("active") is True and glm_status.get("execution_allowed") is False
        add(checks, "Runtime GLM advisory ativo", glm_ok and glm_active, f"active={glm_status.get('active') if isinstance(glm_status, dict) else None}; execution_allowed={glm_status.get('execution_allowed') if isinstance(glm_status, dict) else None}")
        activation_ok, activation = endpoint("http://127.0.0.1:8765/api/activation")
        matrix_path = activation.get("matrix", {}).get("path") if isinstance(activation, dict) and isinstance(activation.get("matrix"), dict) else None
        add(checks, "Homepage Matriz V22", activation_ok and matrix_path == "desktop/ui/matriz_v22/index.html", f"matrix={matrix_path}")
        knowledge_ok, knowledge_status = endpoint("http://127.0.0.1:8765/api/knowledge/status")
        pending_count = knowledge_status.get("pending_human_review") if isinstance(knowledge_status, dict) else None
        approved_count = knowledge_status.get("approved_for_agent") if isinstance(knowledge_status, dict) else None
        add(checks, "Gate de conhecimento", knowledge_ok and pending_count is not None and approved_count == 0 and knowledge_status.get("execution_allowed") is False, f"pending={pending_count}; approved={approved_count}")
        last = checks
        if all(item["ok"] for item in checks):
            report(checks, "AURA_SELF_TEST_FINAL")
            return 0
        time.sleep(2)
    report(last, "AURA_SELF_TEST_FINAL_TIMEOUT")
    return 1


def report(checks: list[dict[str, Any]], title: str) -> None:
    print(f"=== {title} ===")
    for item in checks:
        prefix = "OK" if item["ok"] else ("AVISO" if item["warning"] else "FALHA")
        print(f"[{prefix}] {item['name']}: {item['detail']}")
    print(json.dumps({"title": title, "ok": all(i["ok"] or i["warning"] for i in checks), "checks": checks}, ensure_ascii=False, indent=2))


def finish(checks: list[dict[str, Any]]) -> int:
    return 0 if all(item["ok"] or item["warning"] for item in checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--phase", choices=("pre", "post", "final"), default=None)
    parser.add_argument("--wait", type=int, default=90)
    args = parser.parse_args()
    root_value = args.root or os.getenv("AURA_SELF_TEST_ROOT")
    phase = args.phase or os.getenv("AURA_SELF_TEST_PHASE")
    if not root_value:
        parser.error("informe --root ou AURA_SELF_TEST_ROOT")
    if phase not in {"pre", "post", "final"}:
        parser.error("informe --phase pre/post/final ou AURA_SELF_TEST_PHASE")
    # O CMD pode preservar aspas residuais quando há barra invertida final; normalize antes de usar WinAPI.
    root_value = str(root_value).strip().strip('"').strip("'")
    root = Path(root_value).resolve()
    if phase == "pre":
        return pre_phase(root)
    if phase == "post":
        return post_phase(root)
    return final_phase(root, args.wait)


if __name__ == "__main__":
    raise SystemExit(main())
