"""Revisão estática de código de ferramentas enviadas pelo utilizador.
Nunca executa o código nesta fase. Bloqueia imports e APIs perigosas."""
import ast
import hashlib
import re
from pathlib import Path

from . import paths
from .validators import ValidationError

CODE_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S | re.I)
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
MAX_SOURCE = 80_000

ALLOWED_IMPORTS = {
    "json", "re", "time", "datetime", "math", "hashlib", "typing", "dataclasses",
    "collections", "string", "decimal", "pathlib", "logging", "unicodedata",
    "alfred", "alfred.validators", "alfred.paths", "alfred.config",
    "alfred.registry", "alfred.executor", "alfred.util",
}

FORBIDDEN_MODULES = {
    "subprocess", "ctypes", "socket", "pickle", "winreg", "multiprocessing",
    "shutil", "os", "sys", "importlib", "requests", "http", "httpx", "urllib",
    "webbrowser", "msvcrt", "win32api", "win32com", "powershell", "pty",
    "fcntl", "signal", "builtins", "code", "codeop", "compileall",
}

FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "exit", "quit", "breakpoint",
    "system", "popen", "remove", "unlink", "rmdir", "removedirs", "rmtree",
    "startfile", "kill", "spawn", "Popen", "check_output", "call",
    "setattr", "delattr", "globals", "locals", "vars",
}

REQUIRED_ATTRS = ("TOOL_NAME", "validate", "run")


def extract_code(message: str) -> str:
    text = message or ""
    fences = CODE_FENCE_RE.findall(text)
    if fences:
        return max(fences, key=len).strip()
    return ""


def is_install_intent(text: str) -> bool:
    t = (text or "").lower()
    if extract_code(text) and any(k in t for k in (
            "instala", "instal", "adiciona ferramenta", "nova ferramenta",
            "regista ferramenta", "plugin")):
        return True
    return bool(re.search(
        r"\binstala(?:r)?(?:\s+(?:esta|a|o))?\s+ferramenta\b", t))


def _walk_imports(tree: ast.AST) -> list:
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
    return mods


def _calls(tree: ast.AST) -> list:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.append(f.id)
            elif isinstance(f, ast.Attribute):
                names.append(f.attr)
    return names


def _assign_str(tree: ast.AST, name: str) -> str:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name and isinstance(node.value, ast.Constant):
                    return str(node.value.value)
    return ""


def review_source(source: str, suggested_name: str = "") -> dict:
    src = (source or "").strip()
    blockers, warnings = [], []
    if not src:
        return {"ok": False, "blockers": ["código vazio"], "warnings": [], "manifest": {}}
    if len(src) > MAX_SOURCE:
        return {"ok": False, "blockers": [f"código excede {MAX_SOURCE} caracteres"],
                "warnings": [], "manifest": {}}
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"ok": False, "blockers": [f"syntax error: {e}"], "warnings": [], "manifest": {}}

    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assigned = set()
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    assigned.add(t.id)
    for req in REQUIRED_ATTRS:
        if req == "TOOL_NAME" and req not in assigned:
            blockers.append("falta TOOL_NAME = 'nome_em_snake_case'")
        elif req in ("validate", "run") and req not in defined:
            blockers.append(f"falta def {req}(args, ctx) ou def {req}(args)")

    name = _assign_str(tree, "TOOL_NAME") or (suggested_name or "").strip()
    if name and not NAME_RE.match(name):
        blockers.append(f"TOOL_NAME inválido: {name!r} (use [a-z][a-z0-9_]{{1,40}})")
    if name.startswith("_"):
        blockers.append("TOOL_NAME não pode começar por _")

    for mod in _walk_imports(tree):
        root = (mod or "").split(".")[0]
        if root in FORBIDDEN_MODULES:
            blockers.append(f"import proibido: {mod}")
        elif mod and mod not in ALLOWED_IMPORTS and root not in {"alfred", "pathlib", "typing"}:
            blockers.append(f"import fora da allowlist: {mod}")

    for c in _calls(tree):
        if c in FORBIDDEN_CALLS:
            blockers.append(f"chamada proibida: {c}()")

    src_l = src.lower()
    for needle in ("powershell", "cmd.exe", "wscript", "/c start", "os.system"):
        if needle in src_l:
            blockers.append(f"padrão proibido no texto: {needle}")
    if "open(" in src and "resolve_allowed" not in src:
        warnings.append("usa open() sem resolve_allowed — paths devem passar por alfred.validators")
    if "execution_allowed" in src_l and "true" in src_l:
        blockers.append("o plugin não pode alterar execution_allowed")
    if "paper_trade" in src_l and "false" in src_l:
        blockers.append("o plugin não pode desligar paper_trade")

    risk = (_assign_str(tree, "RISK") or "medium").lower()
    if risk not in ("low", "medium", "high"):
        warnings.append(f"RISK {risk!r} inválido — a instalar como medium")
        risk = "medium"
    mutating = _assign_str(tree, "MUTATING").lower() in ("true", "1", "yes") if _assign_str(tree, "MUTATING") else True
    summary = _assign_str(tree, "SUMMARY") or name or "plugin"

    digest = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
    manifest = {
        "name": name or "",
        "risk": risk,
        "mutating": mutating,
        "sensitive": True,
        "summary": summary[:200],
        "sha256_16": digest,
        "bytes": len(src.encode("utf-8")),
    }
    ok = not blockers
    return {"ok": ok, "blockers": blockers, "warnings": warnings, "manifest": manifest}


def write_review(report: dict) -> Path:
    paths.PLUGIN_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    name = (report.get("manifest") or {}).get("name") or "unknown"
    p = paths.PLUGIN_REVIEWS_DIR / f"{name}-{(report.get('manifest') or {}).get('sha256_16') or 'x'}.json"
    from .util import atomic_write_json
    atomic_write_json(p, report)
    return p
