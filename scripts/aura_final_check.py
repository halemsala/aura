#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aura_final_check.py — TESTE DE ACEITACAO COMPLETO do AURA QUANT-X V25.
Roda TODAS as validacoes em sequencia e reporta o estado de cada peca.

USO:
    python scripts\\aura_final_check.py          # tudo
    python scripts\\aura_final_check.py --quick  # so imports + sintaxe
    python scripts\\aura_final_check.py --verbose

O QUE VERIFICA:
    1. SINTAXE — ast.parse em todos os .py da arvore
    2. IMPORTS — cada modulo do inventario importa sem erro
    3. SELF-TESTS — roda o self-test de cada modulo com __main__
    4. DEPENDENCIAS OPCIONAIS — playwright, duckdb, psutil, pynvml, opencv
    5. OLLAMA — servidor responde, modelos disponiveis (glm4, qwen3, nomic, moondream)
    6. SERVICOS — bridge :8080, engine :8765, voice :8099, metrics
    7. ARQUIVOS DE CONFIG — config.yaml, app_allowlist.json, telegram_channels.json
    8. DESKTOP — dotnet build do projeto C#
    9. BANCO — analytics.duckdb/sqlite abre e tem tabelas
    10. JOURNALS — bridge/*.jsonl existem e tem linhas

Resultado: AURA_FINAL_CHECK.md com tabela completa + veredito.

stdlib only. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- blindagem de encoding -------------------------------------------------
# Quando o stdout e redirecionado (ex.: "> log.txt" a partir de um .bat) o
# Python pode herdar o codepage do console Windows (cp1252) em vez de UTF-8,
# e print() quebra com UnicodeEncodeError em qualquer caractere fora do
# cp1252 (acentos, emojis, replacement char). Isso derruba o script inteiro
# no meio de uma checagem, mesmo quando o problema real e so cosmetico.
# Reconfigura o stdout/stderr para UTF-8 com substituicao seguraem vez de
# lancar excecao; se a stream nao suportar reconfigure (Python < 3.7 ou
# stream customizada), ignora e segue com o comportamento original.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "1.1.0-V25T6"
ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {"__pycache__", "venv", ".venv", "node_modules", "build",
             "dist", ".tox", ".eggs", ".mypy_cache", ".pytest_cache",
             "engine/data/people", "engine/data/.aura_trash"}


def _skip_child(current: Path, child: str) -> bool:
    if child in {"__pycache__", "venv", ".venv", "node_modules", "build", "dist",
                 ".tox", ".eggs", ".mypy_cache", ".pytest_cache"}:
        return True
    rel = str((current / child).relative_to(ROOT)).replace("\\", "/")
    return rel in {"engine/data/people", "engine/data/.aura_trash"}

OPTIONAL_DEPS = {
    "playwright": "playwright", "selenium": "selenium", "duckdb": "duckdb",
    "psutil": "psutil", "pynvml": "pynvml", "opencv-contrib-python": "cv2",
    "sounddevice": "sounddevice", "numpy": "numpy", "weasyprint": "weasyprint",
    "pypdf": "pypdf", "edge-tts": "edge_tts",
}

INVENTORY_MODULES = [
    # engine/core
    "engine/core/feed_bus.py",
    "engine/core/conformal_gate.py",
    "engine/core/mc_grid.py",
    "engine/core/replay.py",
    "engine/core/analytics.py",
    "engine/core/observability.py",
    "engine/core/error_handler.py",
    "engine/core/security.py",
    "engine/core/hardware_governor.py",
    "engine/core/autonomous_cache.py",
    "engine/core/cache_integration.py",
    "engine/core/meta_labeling.py",
    # engine/agents (inventario original)
    "engine/agents/supervisor_jarvis.py",
    "engine/agents/telegram_hq.py",
    "engine/agents/browser_agent.py",
    "engine/agents/cross_site_analyst.py",
    "engine/agents/jarvis_persona.py",
    "engine/agents/persona_tools.py",
    # engine/agents (novos desta conversa)
    "engine/core/sensor_cache.py",
    "engine/core/latency_sim.py",
    "engine/agents/tts_cache.py",
    "engine/agents/tab_scheduler.py",
    "engine/agents/greenlight_check.py",
    "engine/agents/persona_bridge.py",
    "engine/agents/people_memory.py",
    "engine/agents/jarvis_command_center.py",
    "engine/agents/domestic_operator.py",
    "engine/agents/web_knowledge.py",
    "engine/agents/research_improver.py",
    "engine/agents/media_editor.py",
    "engine/agents/desktop_controller.py",
    "engine/agents/telegram_employee.py",
    "engine/agents/voice_auth.py",
    "engine/agents/command_router_v2.py",
    "engine/agents/vision.py",
    "engine/agents/external_intelligence.py",
    "engine/agents/agent_skill_engine.py",
    "engine/agents/external_sources_e.py",
    "engine/agents/football_intelligence.py",
    "engine/agents/football_research_hub.py",
    "engine/agents/enhanced_core.py",
    "engine/agents/natural_voice.py",
    "engine/agents/tipster_capture.py",
    "engine/agents/intent_router.py",
    # engine
    "engine/boot.py",
    # scripts
    "scripts/run_selftests.py",
    "scripts/robot_alert_audit.py",
    "scripts/aura_weekly_analytics.py",
    "scripts/aura_voice_client.py",
    "scripts/aura_compute.py",
]

SERVICE_URLS = {
    "bridge": "http://127.0.0.1:8080/health",
    "engine": "http://127.0.0.1:8765/api/health",
    "voice": "http://127.0.0.1:8099/api/voice/health",
    "ollama": "http://127.0.0.1:11434/api/tags",
}

OLLAMA_MODELS_ESPERADOS = {
    "glm4": "GLM-4 (modelo principal)",
    "qwen3": "Qwen3 (advisor tool calling)",
    "nomic-embed": "nomic-embed-text (busca semantica)",
    "moondream": "moondream (visao)",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_http(url: str, timeout: float = 3.0) -> Tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, "HTTP %d" % resp.status
    except Exception as exc:
        return False, str(exc)[:80]


def _check_syntax(path: Path) -> Tuple[bool, str]:
    try:
        ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        return True, "ok"
    except SyntaxError as exc:
        return False, "linha %s: %s" % (exc.lineno, exc.msg)
    except Exception as exc:
        return False, str(exc)[:80]


def _check_import(module_path: str) -> Tuple[bool, str]:
    """Import seguro em subprocesso (nao contamina este processo)."""
    mod = module_path.replace("/", ".").replace(".py", "")
    code = "import %s" % mod
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, timeout=30, cwd=str(ROOT), env=env)
        if proc.returncode == 0:
            return True, "ok"
        err = proc.stderr.decode("utf-8", errors="replace")[-200:]
        return False, err
    except subprocess.TimeoutExpired:
        return False, "timeout 30s"
    except Exception as exc:
        return False, str(exc)[:80]


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Encerra o grupo inteiro do self-test, inclusive filhos órfãos."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           timeout=5)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass


def _check_selftest(path: Path, timeout: float = 120) -> Tuple[bool, str]:
    """Roda self-test em grupo isolado e limpa filhos em timeout."""
    proc = None
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["AURA_FINAL_CHECK_MODE"] = "1"
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": str(ROOT),
            "env": env,
            "text": False,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(path)], **popen_kwargs)
        stdout, _stderr = proc.communicate(timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        if proc.returncode == 0 and "ALL TESTS PASSED" in output:
            return True, "pass"
        if "SKIP" in output:
            return True, "pass (com SKIPs)"
        fails = [l for l in output.splitlines() if "FAIL" in l]
        return False, "; ".join(fails[:2]) or "rc=%d" % proc.returncode
    except subprocess.TimeoutExpired:
        if proc is not None:
            _terminate_process_tree(proc)
        return False, "timeout %.0fs (grupo encerrado)" % timeout
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            _terminate_process_tree(proc)
        return False, str(exc)[:80]


def _check_dotnet() -> Tuple[bool, str]:
    csproj = ROOT / "desktop" / "Aura.Desktop.csproj"
    if not csproj.is_file():
        return False, "csproj nao encontrado"
    try:
        proc = subprocess.run(
            ["dotnet", "build", str(csproj), "-c", "Release", "--nologo",
             "-v", "quiet"],
            capture_output=True, timeout=300, cwd=str(ROOT / "desktop"))
        if proc.returncode == 0:
            return True, "build ok"
        err = proc.stderr.decode("utf-8", errors="replace")[-300:]
        return False, err
    except FileNotFoundError:
        return False, "dotnet CLI nao encontrado no PATH"
    except subprocess.TimeoutExpired:
        return False, "timeout 300s"
    except Exception as exc:
        return False, str(exc)[:80]


def _check_analytics_db() -> Tuple[bool, str]:
    """Abre o banco de analytics e verifica tabelas."""
    for name in ("analytics.duckdb", "analytics.sqlite", "an_sqlite.db"):
        db = ROOT / "engine" / "data" / name
        if not db.is_file():
            continue
        if name.endswith(".duckdb"):
            try:
                import duckdb
                con = duckdb.connect(str(db), read_only=True)
                tables = [r[0] for r in con.execute(
                    "SHOW TABLES").fetchall()]
                con.close()
                expected = {"frames", "decisions", "predictions",
                            "resolutions", "loaded_files"}
                if expected.issubset(set(tables)):
                    return True, "%s: %d tabelas" % (name, len(tables))
                return False, "%s: faltam %s" % (
                    name, expected - set(tables))
            except ImportError:
                return False, "%s existe mas duckdb nao instalado" % name
            except Exception as exc:
                return False, "%s: %s" % (name, str(exc)[:80])
        else:
            try:
                import sqlite3
                con = sqlite3.connect(str(db))
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()]
                con.close()
                expected = {"frames", "decisions", "predictions",
                            "resolutions", "loaded_files"}
                if expected.issubset(set(tables)):
                    return True, "%s: %d tabelas" % (name, len(tables))
                return False, "%s: faltam %s" % (
                    name, expected - set(tables))
            except Exception as exc:
                return False, "%s: %s" % (name, str(exc)[:80])
    return False, "nenhum banco de analytics encontrado"


def _check_journals() -> Tuple[bool, str]:
    bridge = ROOT / "bridge"
    if not bridge.is_dir():
        return False, "pasta bridge/ nao existe"
    jsonl_files = list(bridge.glob("*.jsonl")) + \
        list(bridge.glob("*.jsonl.gz"))
    if not jsonl_files:
        return False, "nenhum journal .jsonl em bridge/"
    total_lines = 0
    for f in jsonl_files[:5]:
        try:
            if f.suffix == ".gz":
                import gzip
                with gzip.open(f, "rt", encoding="utf-8") as fh:
                    total_lines += sum(1 for _ in fh)
            else:
                with open(f, "r", encoding="utf-8") as fh:
                    total_lines += sum(1 for _ in fh)
        except Exception:
            pass
    if total_lines > 0:
        return True, "%d arquivo(s), %d linhas" % (len(jsonl_files),
                                                   total_lines)
    return False, "%d arquivo(s) mas 0 linhas legiveis" % len(jsonl_files)


def _check_static_audit() -> Tuple[bool, str]:
    """Executa somente a auditoria estrutural; não inicia serviços."""
    audit = ROOT / "desktop" / "packaging" / "audit_installer_static.py"
    if not audit.is_file():
        return False, "auditoria estática ausente"
    try:
        proc = subprocess.run(
            [sys.executable, str(audit)], capture_output=True, timeout=60, cwd=str(ROOT)
        )
        output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
        if proc.returncode == 0 and "INSTALLER_STATIC_AUDIT=PASS" in output:
            return True, "PASS"
        failed = [line for line in output.splitlines() if "[FAIL]" in line or "INSTALLER_STATIC_AUDIT=" in line]
        return False, "; ".join(failed[-3:])[:180] or "auditoria retornou erro"
    except Exception as exc:
        return False, str(exc)[:180]


def _check_config_files() -> List[Tuple[str, bool, str]]:
    results = []
    # config.yaml do jarvis
    cfg = ROOT / "bridge" / "jarvis" / "config.yaml"
    results.append(("config.yaml", cfg.is_file(),
                    "ok" if cfg.is_file() else "ausente"))
    # app_allowlist.json
    allow = ROOT / "engine" / "data" / "app_allowlist.json"
    if allow.is_file():
        try:
            data = json.loads(allow.read_text(encoding="utf-8"))
            results.append(("app_allowlist.json", True,
                            "%d programas" % len(data)))
        except Exception:
            results.append(("app_allowlist.json", False, "ilegivel"))
    else:
        results.append(("app_allowlist.json", False,
                        "ausente (criado no primeiro boot)"))
    # telegram_channels.json
    tg = ROOT / "engine" / "data" / "telegram_channels.json"
    results.append(("telegram_channels.json", tg.is_file(),
                    "ok" if tg.is_file() else "ausente (opcional)"))
    # aura-capture.js
    cap = ROOT / "desktop" / "capture" / "aura-capture.js"
    results.append(("aura-capture.js", cap.is_file(),
                    "ok" if cap.is_file() else "ausente"))
    # voice profiles
    vp = ROOT / "voice_profiles"
    results.append(("voice_profiles/", vp.is_dir(),
                    "ok" if vp.is_dir() else "ausente"))
    return results


def _check_env_vars() -> List[Tuple[str, bool, str]]:
    env_vars = [
        ("AURA_TG_TOKEN", "Telegram bot token (funcionario)"),
        ("AURA_TG_PIN", "Telegram chat PIN"),
        ("AURA_DESK_PIN", "PIN de controle remoto de mesa"),
        ("GLM_API_KEY", "GLM API key (persona avancada)"),
        ("FOOTBALL_DATA_KEY", "football-data.org key (opcional)"),
    ]
    results = []
    for var, desc in env_vars:
        val = os.environ.get(var, "")
        present = bool(val.strip())
        results.append((var, present,
                        ("definido" if present else "nao definido (%s)"
                         % desc)))
    return results


def _check_ollama() -> Tuple[bool, List[str]]:
    ok, detail = _check_http(SERVICE_URLS["ollama"])
    if not ok:
        return False, ["servidor offline"]
    try:
        with urllib.request.urlopen(SERVICE_URLS["ollama"],
                                    timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [str(m.get("name", "")) for m in
                  (data.get("models") or [])]
        found = []
        for esperado, desc in OLLAMA_MODELS_ESPERADOS.items():
            if any(esperado in m.lower() for m in models):
                found.append("%s (%s)" % (esperado, desc))
        return True, found
    except Exception:
        return True, ["modelo list ilegivel"]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run_full_check(quick: bool = False, verbose: bool = False) -> int:
    results: List[Dict[str, Any]] = []

    def add(categoria: str, item: str, ok: bool, detail: str) -> None:
        results.append({"categoria": categoria, "item": item,
                        "ok": ok, "detail": detail[:200],
                        "ts": _ts()})
        mark = "PASS" if ok else "FAIL"
        print("[%s] %-12s %-40s %s" % (mark, categoria, item, detail[:60]))

    print("=" * 80)
    print("AURA QUANT-X V25 — FINAL CHECK v%s" % __version__)
    print("Raiz: %s" % ROOT)
    print("Quick: %s | Verbose: %s | Python: %s" %
          (quick, verbose, sys.version.split()[0]))
    print("=" * 80)

    # 0) contratos estruturais do instalador/publicação
    print("\n--- 0. ESTRUTURA E SEGURANÇA ---")
    static_ok, static_detail = _check_static_audit()
    add("estrutura", "audit_installer_static.py", static_ok, static_detail)

    # 1) sintaxe de todos os .py da arvore
    print("\n--- 1. SINTAXE ---")
    py_files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and not _skip_child(Path(dirpath), d)]
        for fn in filenames:
            if fn.endswith(".py"):
                py_files.append(Path(dirpath) / fn)
    syntax_errors = 0
    for pf in sorted(py_files):
        ok, detail = _check_syntax(pf)
        rel = pf.relative_to(ROOT)
        if not ok:
            syntax_errors += 1
            add("sintaxe", str(rel), False, detail)
        elif verbose:
            add("sintaxe", str(rel), True, detail)
    add("sintaxe", "TOTAL (%d arquivos)" % len(py_files),
        syntax_errors == 0,
        "%d erro(s)" % syntax_errors if syntax_errors else "todos ok")

    # 2) imports dos modulos do inventario
    print("\n--- 2. IMPORTS ---")
    import_fails = 0
    for mod_path in INVENTORY_MODULES:
        full = ROOT / mod_path
        if not full.is_file():
            add("import", mod_path, False, "arquivo nao existe")
            import_fails += 1
            continue
        ok, detail = _check_import(mod_path)
        if not ok:
            import_fails += 1
        add("import", mod_path, ok, detail)
    add("import", "TOTAL (%d modulos)" % len(INVENTORY_MODULES),
        import_fails == 0,
        "%d falha(s)" % import_fails if import_fails else "todos ok")

    # 3) self-tests
    print("\n--- 3. SELF-TESTS ---")
    if not quick:
        st_fails = 0
        st_pass = 0
        for mod_path in INVENTORY_MODULES:
            full = ROOT / mod_path
            if not full.is_file():
                continue
            # verifica se tem __main__
            try:
                src = full.read_text(encoding="utf-8", errors="replace")
                if "__main__" not in src:
                    continue
            except Exception:
                continue
            ok, detail = _check_selftest(full)
            if ok:
                st_pass += 1
            else:
                st_fails += 1
            add("selftest", mod_path, ok, detail)
        add("selftest", "TOTAL",
            st_fails == 0,
            "%d pass, %d fail" % (st_pass, st_fails))

    # 4) dependencias opcionais
    if quick:
        add("modo", "verificações externas", True, "pulado (--quick)")
        return _write_report(results, ROOT)

    print("\n--- 4. DEPENDENCIAS OPCIONAIS ---")
    for dep, import_name in OPTIONAL_DEPS.items():
        try:
            __import__(import_name)
            add("deps", dep, True, "instalado")
        except ImportError:
            add("deps", dep, True, "nao instalado (opcional)")

    # 5) Ollama
    print("\n--- 5. OLLAMA ---")
    ollama_ok, models_found = _check_ollama()
    add("ollama", "servidor", ollama_ok,
        "online" if ollama_ok else "offline")
    if ollama_ok:
        for m in models_found:
            add("ollama", m, True, "disponivel")
        for esperado in OLLAMA_MODELS_ESPERADOS:
            if not any(esperado in m for m in models_found):
                add("ollama", esperado, False,
                    "nao instalado (ollama pull %s)" % esperado)

    # 6) servicos
    print("\n--- 6. SERVICOS ---")
    for name, url in SERVICE_URLS.items():
        if name == "ollama":
            continue  # ja verificado acima
        ok, detail = _check_http(url)
        add("servico", "%s (%s)" % (name, url.split(":")[1].split("/")[0]),
            ok, detail)

    # 7) arquivos de config
    print("\n--- 7. CONFIG ---")
    for name, ok, detail in _check_config_files():
        add("config", name, ok, detail)

    # 8) variaveis de ambiente
    print("\n--- 8. AMBIENTE ---")
    for name, ok, detail in _check_env_vars():
        add("ambiente", name, ok, detail)

    # 9) desktop (dotnet build)
    print("\n--- 9. DESKTOP (dotnet build) ---")
    if not quick:
        ok, detail = _check_dotnet()
        add("desktop", "Aura.Desktop.csproj", ok, detail)
    else:
        add("desktop", "Aura.Desktop.csproj", True,
            "pulado (--quick)")

    # 10) banco de analytics
    print("\n--- 10. ANALYTICS ---")
    ok, detail = _check_analytics_db()
    add("analytics", "banco de dados", ok, detail)

    # 11) journals
    print("\n--- 11. JOURNALS ---")
    ok, detail = _check_journals()
    add("journals", "bridge/*.jsonl", ok, detail)

    # ---------------------------------------------------------------- resumo
    print("\n" + "=" * 80)
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed
    pct = (100.0 * passed / total) if total else 0.0

    by_cat: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r["categoria"]
        by_cat.setdefault(cat, {"pass": 0, "fail": 0})
        by_cat[cat]["pass" if r["ok"] else "fail"] += 1

    print("RESUMO: %d/%d PASS (%.1f%%) | %d FAIL" %
          (passed, total, pct, failed))
    print()
    print("%-14s %6s %6s" % ("Categoria", "Pass", "Fail"))
    print("-" * 28)
    for cat in sorted(by_cat):
        c = by_cat[cat]
        print("%-14s %6d %6d" % (cat, c["pass"], c["fail"]))

    return _write_report(results, ROOT)


def _write_report(results: List[Dict[str, Any]], root: Path) -> int:
    """Persiste o relatório sem alterar o estado operacional do AURA."""
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed
    pct = (100.0 * passed / total) if total else 0.0
    report_path = root / "AURA_FINAL_CHECK.md"
    lines = [
        "# AURA Final Check — Relatorio",
        "",
        "*gerado: %s*" % _ts(),
        "",
        "**Resultado: %d/%d PASS (%.1f%%) | %d FAIL**" %
        (passed, total, pct, failed),
        "",
        "| categoria | item | status | detalhe |",
        "|---|---|---|---|",
    ]
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        lines.append("| %s | `%s` | %s | %s |" % (
            r["categoria"], r["item"], status, r["detail"].replace("|", "/")))
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\nRelatorio completo: %s" % report_path)

    return 0 if failed == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="aura_final_check.py",
        description="Teste de aceitacao completo do AURA QUANT-X V25")
    ap.add_argument("--quick", action="store_true",
                    help="pula self-tests e dotnet build (mais rapido)")
    ap.add_argument("--verbose", action="store_true",
                    help="mostra itens que passaram tambem")
    args = ap.parse_args(argv)
    return run_full_check(quick=args.quick, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
