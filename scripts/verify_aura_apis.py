#!/usr/bin/env python3
"""
verify_aura_apis.py — Verifica APIs reais do AURA vs assunções do MORA.
Custo: ZERO. Só leitura estática (AST) + checks de sistema.
Dependências do próprio script: SÓ stdlib Python.
"""
from __future__ import annotations
import ast
import importlib
import json
import os
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
ROOT = Path(__file__).resolve().parent.parent
# ============================================================================
# O QUE O MORA ASSUME
# ============================================================================
@dataclass
class FileExpectation:
    path: str
    classes: Dict[str, List[str]] = field(default_factory=dict)
    functions: List[str] = field(default_factory=list)
    cli_flags: List[str] = field(default_factory=list)
    notes: str = ""
EXPECTATIONS: List[FileExpectation] = [
    FileExpectation(
        path="engine/agent_registry.py",
        classes={"AgentRegistry": ["set_status", "list_agents", "invoke"]},
        notes="CRITICO: MORA precisa de set_status(name, status) para pausar/retomar agentes.",
    ),
    FileExpectation(
        path="engine/gpu_resource_manager.py",
        classes={"GpuResourceManager": ["cuda_info", "resolve_cuda_device", "status"]},
        notes="MORA usa cuda_info() para alocar 85% VRAM.",
    ),
    FileExpectation(
        path="engine/sre/omnipotent_health_profiler.py",
        classes={"OmnipotentHealthProfiler": [
            "run_full_diagnostic",
            "check_memory_fragmentation",
            "check_vram_fragmentation",
            "predict_time_to_failure",
        ]},
        notes="MORA Fase 1 chama run_full_diagnostic().",
    ),
    FileExpectation(
        path="scripts/aura_quality_audit.py",
        functions=["main"],
        cli_flags=["--json"],
        notes="MORA chama via subprocess com --json.",
    ),
    FileExpectation(
        path="bridge/server.py",
        functions=["extract_match_view", "fingerprint", "window_label"],
        notes="FeedbackConnector usa para parsing de REGs.",
    ),
    FileExpectation(
        path="engine/execution_router.py",
        classes={"ExecutionRouter": ["execute"]},
        notes="InvariantGate integra aqui.",
    ),
]
FREE_DEPS: Dict[str, Dict[str, str]] = {
    "torch": {
        "purpose": "Redes neurais (neural_core.py)",
        "install_cpu": "pip install torch --index-url https://download.pytorch.org/whl/cpu",
        "install_gpu": "pip install torch",
    },
    "psutil": {
        "purpose": "Monitorizacao de sistema",
        "install": "pip install psutil",
    },
    "pynvml": {
        "purpose": "GPU monitoring (alternativa a cuda_info)",
        "install": "pip install nvidia-ml-py",
    },
    "aiohttp": {
        "purpose": "HTTP async para pesquisa web",
        "install": "pip install aiohttp",
    },
    "pydantic": {
        "purpose": "Validacao de tipos (GatedDecision)",
        "install": "pip install pydantic",
    },
    "yaml": {
        "purpose": "Leitura de YAML config",
        "install": "pip install pyyaml",
    },
}
# ============================================================================
# LEITURA SEGURA DE FICHEIROS (lida com BOM)
# ============================================================================
def read_source(path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Lê ficheiro Python. Stripa BOM se existir. Retorna (source, error)."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        return None, str(e)
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as e:
        return None, f"UnicodeDecodeError: {e}"
# ============================================================================
# ANÁLISE AST
# ============================================================================
@dataclass
class ClassInfo:
    name: str
    methods: List[str] = field(default_factory=list)
    async_methods: Set[str] = field(default_factory=set)
@dataclass
class AnalysisResult:
    exists: bool
    parse_error: Optional[str] = None
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    functions: List[str] = field(default_factory=list)
    async_functions: Set[str] = field(default_factory=set)
    cli_flags: Dict[str, bool] = field(default_factory=dict)
def analyze_file(path: Path, flags: Optional[List[str]] = None) -> AnalysisResult:
    """Análise estática via AST. Não executa o ficheiro."""
    result = AnalysisResult(exists=path.exists())
    if not result.exists:
        return result
    source, error = read_source(path)
    if error:
        result.parse_error = error
        return result
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        result.parse_error = f"SyntaxError: {e}"
        return result
    except Exception as e:
        result.parse_error = str(e)
        return result
    # Classes
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            info = ClassInfo(name=node.name)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    info.methods.append(item.name)
                    if isinstance(item, ast.AsyncFunctionDef):
                        info.async_methods.add(item.name)
            result.classes[node.name] = info
    # Funções top-level
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.functions.append(node.name)
            if isinstance(node, ast.AsyncFunctionDef):
                result.async_functions.add(node.name)
    # CLI flags (busca textual)
    if flags:
        for flag in flags:
            result.cli_flags[flag] = flag in source
    return result
# ============================================================================
# CHECKS DE SISTEMA
# ============================================================================
def check_import(name: str) -> Tuple[bool, str]:
    """Tenta importar módulo. Retorna (ok, version)."""
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "unknown")
        return True, version
    except ImportError:
        return False, "not installed"
    except Exception as e:
        return False, f"error: {e}"
def check_subprocess(cmd: List[str], timeout: int = 5) -> Tuple[bool, str]:
    """Corre comando, retorna (ok, output)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=timeout, shell=False,
        )
        if result.returncode == 0:
            return True, result.stdout.decode("utf-8", errors="replace").strip()
        return False, result.stderr.decode("utf-8", errors="replace").strip()
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)
def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Verifica se porta está aberta."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()
def check_http(url: str, timeout: float = 2.0) -> bool:
    """Verifica se URL responde."""
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False
def check_nvidia_smi() -> Tuple[bool, str]:
    """Verifica nvidia-smi."""
    cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
           "--format=csv,noheader,nounits"]
    ok, output = check_subprocess(cmd, timeout=5)
    return ok, output
# ============================================================================
# RELATÓRIO
# ============================================================================
def build_report() -> Dict[str, Any]:
    """Constrói relatório completo."""
    report: Dict[str, Any] = {
        "files": [],
        "deps": {},
        "system": {},
        "gaps": [],
        "summary": {"critical": 0, "important": 0, "files_ok": 0},
    }
    # === SISTEMA ===
    nv_ok, nv_out = check_nvidia_smi()
    report["system"] = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "root": str(ROOT),
        "nvidia_smi": nv_ok,
        "nvidia_info": nv_out if nv_ok else None,
        "ollama": check_http("http://127.0.0.1:11434/api/tags", timeout=2),
        "engine_port": check_port("127.0.0.1", 8765, timeout=1),
        "bridge_port": check_port("127.0.0.1", 8080, timeout=1),
    }
    # pip
    pip_ok, _ = check_subprocess([sys.executable, "-m", "pip", "--version"], timeout=5)
    report["system"]["pip"] = pip_ok
    # === FICHEIROS ===
    for exp in EXPECTATIONS:
        path = ROOT / exp.path
        analysis = analyze_file(path, exp.cli_flags)
        file_rpt: Dict[str, Any] = {
            "file": exp.path,
            "exists": analysis.exists,
            "parse_error": analysis.parse_error,
            "classes": {},
            "missing_methods": [],
            "missing_functions": [],
            "cli_flags": analysis.cli_flags,
            "all_clear": False,
            "notes": exp.notes,
        }
        if analysis.exists and not analysis.parse_error:
            all_ok = True
            for cls_name, expected_methods in exp.classes.items():
                if cls_name in analysis.classes:
                    found = analysis.classes[cls_name]
                    file_rpt["classes"][cls_name] = sorted(found.methods)
                    missing = set(expected_methods) - set(found.methods)
                    if missing:
                        file_rpt["missing_methods"].extend(
                            f"{cls_name}.{m}" for m in sorted(missing)
                        )
                        all_ok = False
                else:
                    file_rpt["missing_methods"].append(
                        f"{cls_name} (CLASSE NAO ENCONTRADA)"
                    )
                    all_ok = False
            if exp.functions:
                found_funcs = set(analysis.functions)
                missing = set(exp.functions) - found_funcs
                if missing:
                    file_rpt["missing_functions"] = sorted(missing)
                    all_ok = False
            for flag, found in analysis.cli_flags.items():
                if not found:
                    all_ok = False
            file_rpt["all_clear"] = all_ok
            if all_ok:
                report["summary"]["files_ok"] += 1
        report["files"].append(file_rpt)
    # === DEPENDÊNCIAS ===
    for dep_name, dep_info in FREE_DEPS.items():
        installed, version = check_import(dep_name)
        report["deps"][dep_name] = {
            "purpose": dep_info["purpose"],
            "installed": installed,
            "version": version if installed else None,
            "install": dep_info.get("install", dep_info.get("install_cpu", "")),
        }
    # === GAPS ===
    gaps: List[Dict[str, str]] = []
    # set_status
    ar = next((f for f in report["files"] if "agent_registry" in f["file"]), None)
    if ar and any("set_status" in m for m in ar.get("missing_methods", [])):
        gaps.append({
            "file": "engine/agent_registry.py",
            "missing": "set_status()",
            "severity": "CRITICAL",
            "alternative": "Wrapper direto no manifest JSON (~20 linhas)",
            "install": "nenhuma",
        })
    # cuda_info
    gr = next((f for f in report["files"] if "gpu_resource" in f["file"]), None)
    if gr and any("cuda_info" in m for m in gr.get("missing_methods", [])):
        if report["system"]["nvidia_smi"]:
            alt = "nvidia-smi via subprocess — gratuito, sem install"
            inst = "nenhuma — nvidia-smi ja disponivel"
        else:
            alt = "pip install nvidia-ml-py (pynvml) — gratuito"
            inst = "pip install nvidia-ml-py"
        gaps.append({
            "file": "engine/gpu_resource_manager.py",
            "missing": "cuda_info()",
            "severity": "CRITICAL",
            "alternative": alt,
            "install": inst,
        })
    # run_full_diagnostic
    hp = next((f for f in report["files"] if "health_profiler" in f["file"]), None)
    if hp and any("run_full_diagnostic" in m for m in hp.get("missing_methods", [])):
        gaps.append({
            "file": "engine/sre/omnipotent_health_profiler.py",
            "missing": "run_full_diagnostic()",
            "severity": "IMPORTANT",
            "alternative": "Implementar com psutil + nvidia-smi (~50 linhas)",
            "install": "pip install psutil",
        })
    # --json
    qa = next((f for f in report["files"] if "quality_audit" in f["file"]), None)
    if qa and qa.get("cli_flags", {}).get("--json") is False:
        gaps.append({
            "file": "scripts/aura_quality_audit.py",
            "missing": "--json flag",
            "severity": "IMPORTANT",
            "alternative": "Modificar script (~10 linhas) ou parse regex",
            "install": "nenhuma",
        })
    # torch
    if not report["deps"].get("torch", {}).get("installed"):
        has_gpu = report["system"]["nvidia_smi"]
        if has_gpu:
            inst = "pip install torch"
            alt = "PyTorch GPU (~2GB, gratuito)"
        else:
            inst = "pip install torch --index-url https://download.pytorch.org/whl/cpu"
            alt = "PyTorch CPU (~150MB, gratuito, sem GPU)"
        gaps.append({
            "file": "agents/neural_core.py",
            "missing": "torch",
            "severity": "IMPORTANT",
            "alternative": alt,
            "install": inst,
        })
    # Ollama
    if not report["system"]["ollama"]:
        gaps.append({
            "file": "agents/glm_analysis_agent.py",
            "missing": "Ollama (GLM local)",
            "severity": "CRITICAL",
            "alternative": "Baixar de ollama.ai — gratuito. ollama pull glm-4.7-flash",
            "install": "ollama pull glm-4.7-flash",
        })
    for gap in gaps:
        if gap["severity"] == "CRITICAL":
            report["summary"]["critical"] += 1
        else:
            report["summary"]["important"] += 1
    report["gaps"] = gaps
    return report
# ============================================================================
# OUTPUT
# ============================================================================
def print_report(report: Dict[str, Any], verbose: bool) -> None:
    s = report["system"]
    print("=" * 70)
    print("VERIFICACAO DE APIs DO AURA vs ASSUNCOES DO MORA")
    print("=" * 70)
    print()
    print("SISTEMA:")
    print(f" Python: {s['python']}")
    print(f" Platform: {s['platform']}")
    print(f" Root: {s['root']}")
    print(f" pip: {'OK' if s['pip'] else 'INDISPONIVEL'}")
    print(f" nvidia-smi: {'OK' if s['nvidia_smi'] else 'NAO ENCONTRADO'}")
    if s.get("nvidia_info"):
        print(f" GPU: {s['nvidia_info']}")
    print(f" Ollama: {'A CORRER' if s['ollama'] else 'PARADO'}")
    print(f" Engine :8765: {'ABERTA' if s['engine_port'] else 'FECHADA'}")
    print(f" Bridge :8080: {'ABERTA' if s['bridge_port'] else 'FECHADA'}")
    print()
    print("FICHEIROS DO AURA:")
    for f in report["files"]:
        if f["exists"] and not f["parse_error"] and f["all_clear"]:
            status = "OK"
        elif f["exists"] and not f["parse_error"]:
            status = "GAPS"
        elif f["exists"]:
            status = "ERRO"
        else:
            status = "NAO EXISTE"
        print(f"\n [{status}] {f['file']}")
        if not f["exists"]:
            continue
        if f["parse_error"]:
            print(f" ERRO: {f['parse_error']}")
            continue
        for cls_name, methods in f.get("classes", {}).items():
            print(f" {cls_name}: {len(methods)} metodos")
            if verbose:
                for m in methods:
                    print(f" - {m}")
        if f["missing_methods"]:
            print(f" FALTA: {', '.join(f['missing_methods'])}")
        elif f.get("classes"):
            print(" Todos os metodos: ENCONTRADOS")
        if f["missing_functions"]:
            print(f" FUNCOES EM FALTA: {', '.join(f['missing_functions'])}")
        for flag, found in f.get("cli_flags", {}).items():
            print(f" {flag}: {'OK' if found else 'EM FALTA'}")
        if verbose and f.get("notes"):
            print(f" NOTAS: {f['notes']}")
    print("\nDEPENDENCIAS GRATUITAS:")
    for name, info in report["deps"].items():
        status = "OK" if info["installed"] else "FALTA"
        ver = f" v{info['version']}" if info["installed"] else ""
        print(f" [{status}] {name}{ver}")
        print(f" {info['purpose']}")
        if not info["installed"]:
            print(f" Instalar: {info['install']}")
    print("\nGAPS:")
    summary = report["summary"]
    print(f" CRITICAL: {summary['critical']}")
    print(f" IMPORTANT: {summary['important']}")
    print(f" Files OK: {summary['files_ok']}/{len(report['files'])}")
    for gap in report["gaps"]:
        icon = "[!!!]" if gap["severity"] == "CRITICAL" else "[!]"
        print(f"\n {icon} {gap['file']}: falta {gap['missing']}")
        print(f" Alternativa: {gap['alternative']}")
        print(f" Instalar: {gap['install']}")
    print("\n" + "=" * 70)
    total = summary["critical"] + summary["important"]
    if total == 0:
        print("TUDO OK — pronto para integrar MORA")
    elif summary["critical"] > 0:
        print(f"ATENCAO: {summary['critical']} CRITICAL — resolver antes de prosseguir")
    else:
        print(f"{summary['important']} IMPORTANT — pode prosseguir com cuidado")
    print("=" * 70)
# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Verifica APIs do AURA")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(report, verbose=args.verbose)
    return 1 if report["summary"]["critical"] > 0 else 0
if __name__ == "__main__":
    sys.exit(main())
