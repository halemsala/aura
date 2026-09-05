#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V9 Chat FULL + API local :8777  —  V1.2.0 HUMAN + FULL ACCESS (paper-safe)
================================================================================
GET  /health
GET  /chat          → UI HTML de chat
POST /api/chat      → {message} → resposta humana + acoes
POST /api/prompt    → {prompt}  → interpreta desejo
POST /api/correct   → {code}    → aplica correcao allowlist
POST /api/cycle     → ciclo diagnostico
GET  /api/latest    → ultimo relatorio
GET  /api/policy    → policy treinada V9
GET  /api/allowlist → lista de acoes
POST /api/fs/read   → {path}    → le ficheiro sob ROOT
POST /api/fs/list   → {path}    → lista pasta
POST /api/fs/write  → {path, content} → escreve (safe paths)

Invariantes HARD: paper_trade=true | execution_allowed=false
Nunca liga execucao real de apostas.
Acesso amplo de leitura e edicao segura a todo o AURA.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

VERSION = "Hermes-V9-Chat-FULL-1.3.0-OPERATOR"
PORT = int(os.environ.get("HERMES_API_PORT", "8777"))

# --- Safe correction allowlist ---
ALLOWLIST = {
    "domain_lock": {
        "desc": "Grava prompt futebol-only (anti alucinacao bolsa)",
        "action": "domain_lock",
    },
    "train_v9": {
        "desc": "Treina policy Hermes V9 com logs locais",
        "action": "train_v9",
    },
    "run_v9_max": {
        "desc": "Corre crew V9 MAX (Scanner..Sentinel)",
        "action": "run_v9_max",
    },
    "run_swarm": {
        "desc": "Corre Hermes Swarm V32",
        "action": "run_swarm",
    },
    "run_supervisor": {
        "desc": "Corre Hermes Supervisor --once",
        "action": "run_supervisor",
    },
    "run_deep": {
        "desc": "Diagnostico profundo",
        "action": "run_deep",
    },
    "full_stack": {
        "desc": "Treino + V9 MAX + Swarm + Deep (capacidade total)",
        "action": "full_stack",
    },
    "fix_desktop_json": {
        "desc": "Homepage Matriz → http://127.0.0.1:8766 (anti-404)",
        "action": "fix_desktop_json",
    },
    "status": {
        "desc": "Estado geral (portas, health, live)",
        "action": "status",
    },
    "latest": {
        "desc": "Ultimos relatorios",
        "action": "latest",
    },
}


def find_root() -> Path:
    env = os.environ.get("AURA_ROOT")
    cands = [Path(env)] if env else []
    cands += [Path(r"C:\aura"), Path.cwd(), Path(__file__).resolve().parents[1]]
    for c in cands:
        if c and (c / "engine" / "server.py").exists():
            return c.resolve()
    return Path.cwd().resolve()


ROOT = find_root()


def _bootstrap_clean_install() -> None:
    """Garante dirs e seed paper-demo para instalacao limpa."""
    try:
        for rel in ("bridge", "logs_supervisor", "engine/data", "engine/prompts", "engine/agents"):
            (ROOT / rel).mkdir(parents=True, exist_ok=True)
        live = ROOT / "bridge" / "live_latest.json"
        if not live.exists():
            demo = {
                "mode": "paper_demo",
                "status": "idle",
                "source": "chat_api_bootstrap",
                "home": "Demo Home FC",
                "away": "Demo Away United",
                "teams": ["Demo Home FC", "Demo Away United"],
                "corner_events": [],
                "events": [],
                "corners": {"home": 0, "away": 0, "total": 0},
                "note": "Seed automatico instalacao limpa",
            }
            live.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt = ROOT / "engine" / "prompts" / "system_hermes_football_only.txt"
        if not prompt.exists():
            prompt.write_text(
                "# Hermes domain lock — futebol/escanteios only\n"
                "paper_trade=true\nexecution_allowed=false\n"
                "PROIBIDO: bolsa, tickers, ordens reais.\n",
                encoding="utf-8",
            )
    except Exception:
        pass


_bootstrap_clean_install()


def _env() -> dict:
    e = os.environ.copy()
    e["PAPER_TRADE"] = "true"
    e["EXECUTION_ALLOWED"] = "false"
    e["GLM_ADVISORY_ONLY"] = "true"
    e["AURA_ROOT"] = str(ROOT)
    e["PYTHONUTF8"] = "1"
    return e


def _py() -> str:
    p = ROOT / "engine" / "venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else sys.executable


def _run_py(script_rel: str, args: Optional[List[str]] = None, timeout: int = 180) -> Dict[str, Any]:
    script = ROOT / script_rel
    if not script.exists():
        cmd = [_py(), "-m", script_rel] + (args or [])
    else:
        cmd = [_py(), str(script)] + (args or [])
    try:
        r = subprocess.run(
            cmd, cwd=str(ROOT), env=_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return {
            "ok": r.returncode in (0, 1),
            "returncode": r.returncode,
            "stdout": (r.stdout or "")[-4000:],
            "stderr": (r.stderr or "")[-1500:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _safe_resolve(rel_or_abs: str) -> Optional[Path]:
    """Resolve path sob ROOT apenas. Bloqueia path traversal."""
    try:
        raw = (rel_or_abs or "").strip().replace("\\", "/")
        if not raw or ".." in raw.split("/"):
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        else:
            p = p.resolve()
        root_s = str(ROOT.resolve())
        if not str(p).startswith(root_s):
            return None
        return p
    except Exception:
        return None


# Paths onde escrita e permitida (paper-safe)
_WRITE_ALLOWED_PREFIXES = (
    "engine/prompts",
    "engine/data",
    "bridge",
    "logs_supervisor",
    "desktop/config",
    "scripts",
    "config",
)


def _write_allowed(p: Path) -> bool:
    try:
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        return any(rel == pref or rel.startswith(pref + "/") for pref in _WRITE_ALLOWED_PREFIXES)
    except Exception:
        return False


def apply_correction(code: str) -> Dict[str, Any]:
    """Aplica correcao da allowlist."""
    if code not in ALLOWLIST:
        return {
            "ok": False,
            "error": "not_in_allowlist",
            "allowed": list(ALLOWLIST.keys()),
            "hint": "So acoes da allowlist. execution_allowed permanece false.",
        }
    action = ALLOWLIST[code]["action"]

    if action == "domain_lock":
        p = ROOT / "engine" / "prompts"
        p.mkdir(parents=True, exist_ok=True)
        target = p / "system_hermes_football_only.txt"
        target.write_text(
            "# SYSTEM PROMPT — AURA / HERMES OPERATOR\n"
            "Papel principal: diagnostico, saude, logs, correcoes e operacao do sistema AURA QUANT-X.\n"
            "Podes falar de: portas, Bridge, Engine, Matriz, Voice, Ollama, venv, configs,\n"
            "captura, live_latest, agents, policy, desktop, scripts, erros, 404, restarts.\n"
            "Modulo de mercado (quando ativo): futebol/escanteios/SokkerPRO em paper-trade.\n"
            "PROIBIDO: apostas reais, execution_allowed=true, ordens reais, bolsa/tickers.\n"
            "Invariantes: paper_trade=true · execution_allowed=false\n"
            "Respostas: PT-BR, diretas, operacionais.\n",
            encoding="utf-8",
        )
        return {"ok": True, "applied": code, "path": str(target)}

    if action == "train_v9":
        return {"ok": True, "applied": code, **_run_py("engine/agents/hermes_v9_trainer.py", ["--root", str(ROOT)])}

    if action == "run_v9_max":
        return {"ok": True, "applied": code, **_run_py("engine/agents/hermes_agents_v9_max.py", ["--root", str(ROOT)])}

    if action == "run_swarm":
        return {"ok": True, "applied": code, **_run_py("engine/agents/hermes_swarm_v32.py", ["--root", str(ROOT)])}

    if action == "run_supervisor":
        return {"ok": True, "applied": code, **_run_py("engine.agents.hermes_supervisor_agent", ["--once"])}

    if action == "run_deep":
        return {"ok": True, "applied": code, **_run_py("scripts/hermes_deep_diagnostic.py", ["--root", str(ROOT), "--deep", "--report"])}

    if action == "fix_desktop_json":
        cfg = ROOT / "desktop" / "config" / "desktop.json"
        if not cfg.exists():
            return {"ok": False, "error": "desktop.json missing"}
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            app = data.setdefault("app", {})
            app["homepage"] = "http://127.0.0.1:8766/index.html"
            app["fallbackHomepages"] = [
                "http://127.0.0.1:8766/index.html",
                "http://127.0.0.1:8766/",
                "https://aura.local/",
            ]
            cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "applied": code, "path": str(cfg)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if action == "full_stack":
        steps = []
        for c in ("domain_lock", "fix_desktop_json", "train_v9", "run_v9_max", "run_swarm", "run_deep"):
            steps.append({"code": c, "result": apply_correction(c)})
        ok = all((s["result"] or {}).get("ok") for s in steps)
        return {"ok": ok, "applied": "full_stack", "steps": steps}

    if action == "status":
        return {"ok": True, "applied": "status", **_system_status()}

    if action == "latest":
        return {"ok": True, "applied": "latest", **_latest_reports()}

    return {"ok": False, "error": "unknown_action"}


def _system_status() -> Dict[str, Any]:
    import socket

    def port_up(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            return False

    ports = {
        "bridge:8080": port_up(8080),
        "engine:8765": port_up(8765),
        "matriz:8766": port_up(8766),
        "hermes:8777": True,
        "voice:8099": port_up(8099),
        "ollama:11434": port_up(11434),
    }
    live = ROOT / "bridge" / "live_latest.json"
    live_info: Dict[str, Any] = {"exists": live.exists()}
    if live.exists():
        try:
            data = json.loads(live.read_text(encoding="utf-8", errors="replace") or "{}")
            live_info.update({
                "home": data.get("home"),
                "away": data.get("away"),
                "mode": data.get("mode"),
                "corners": len(data.get("corner_events") or []),
                "status": data.get("status") or data.get("period"),
            })
        except Exception as e:
            live_info["error"] = str(e)
    return {
        "root": str(ROOT),
        "ports": ports,
        "live": live_info,
        "paper_trade": True,
        "execution_allowed": False,
    }


def _latest_reports() -> Dict[str, Any]:
    logdir = ROOT / "logs_supervisor"
    out: Dict[str, Any] = {}
    for name in ("HERMES_V9_MAX_LATEST.txt", "HERMES_SWARM_LATEST.txt", "HERMES_DEEP_LATEST.txt",
                 "HERMES_SUPERVISOR_LATEST.txt"):
        p = logdir / name
        if p.exists():
            try:
                out[name] = p.read_text(encoding="utf-8", errors="replace")[-2000:]
            except Exception as e:
                out[name] = f"erro: {e}"
        else:
            out[name] = None
    return {"reports": out}


def _read_file_safe(rel: str, max_chars: int = 12000) -> Dict[str, Any]:
    p = _safe_resolve(rel)
    if not p:
        return {"ok": False, "error": "path_invalido_ou_fora_do_aura"}
    if not p.exists():
        return {"ok": False, "error": "nao_existe", "path": str(p)}
    if p.is_dir():
        return {"ok": False, "error": "e_diretorio_use_list"}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        return {
            "ok": True,
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "size": p.stat().st_size,
            "truncated": truncated,
            "content": text[:max_chars],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _list_dir_safe(rel: str = ".") -> Dict[str, Any]:
    p = _safe_resolve(rel or ".")
    if not p:
        return {"ok": False, "error": "path_invalido"}
    if not p.exists():
        return {"ok": False, "error": "nao_existe"}
    if not p.is_dir():
        return {"ok": False, "error": "nao_e_diretorio"}
    try:
        items = []
        for child in sorted(p.iterdir())[:200]:
            items.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": child.stat().st_size if child.is_file() else None,
            })
        return {
            "ok": True,
            "path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "items": items,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _write_file_safe(rel: str, content: str) -> Dict[str, Any]:
    p = _safe_resolve(rel)
    if not p:
        return {"ok": False, "error": "path_invalido_ou_fora_do_aura"}
    if not _write_allowed(p):
        return {
            "ok": False,
            "error": "escrita_nao_permitida_neste_path",
            "allowed_prefixes": list(_WRITE_ALLOWED_PREFIXES),
        }
    # Bloquear tentativas de liberar execucao real
    low = (content or "").lower()
    if any(x in low for x in ("execution_allowed=true", '"allowrealorders": true', "allow_real_orders: true")):
        return {"ok": False, "error": "bloqueado: tentativa de liberar execution real"}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(p.relative_to(ROOT)).replace("\\", "/"), "bytes": len(content.encode("utf-8"))}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Intent engine — entende o desejo, nao so palavras-chave
# ---------------------------------------------------------------------------

def interpret_intent(text: str) -> Dict[str, Any]:
    """Mapeia linguagem natural → acoes. Fail-closed para trading real."""
    t = (text or "").lower().strip()
    actions: List[str] = []
    meta: Dict[str, Any] = {}

    # Bloqueios duros
    if any(w in t for w in (
        "execution_allowed=true", "aposta real", "live trade", "desligar paper",
        "ordem real", "permitir apostas", "tirar paper", "real money", "bet real"
    )):
        return {"actions": [], "blocked": True, "meta": {}, "reason": "pedido de execucao real bloqueado"}

    # --- full stack / arrumar tudo ---
    if any(w in t for w in (
        "full_stack", "capacidade total", "arruma tudo", "conserta tudo", "corrigir tudo",
        "consertar aura", "fix all", "deixa pronto", "prepara o sistema", "tudo automatico",
        "coloca tudo a funcionar", "sobe tudo"
    )):
        actions = ["domain_lock", "fix_desktop_json", "train_v9", "run_v9_max", "run_swarm", "run_deep"]
        return {"actions": actions, "blocked": False, "meta": {"auto": True}, "reason": "capacidade total"}

    # --- domain lock (anti-bolsa / prompt operador) ---
    if any(w in t for w in ("domain_lock", "domain lock", "alucinacao bolsa", "prompt operador", "anti bolsa")):
        actions.append("domain_lock")

    # --- treino ---
    if any(w in t for w in ("treinar", "treino", "train", "policy", "aprender", "reaprender")):
        actions.append("train_v9")

    # --- diagnosticos ---
    if any(w in t for w in ("diagnost", "deep", "relatorio profundo", "analise profunda", "o que esta mal")):
        actions.append("run_deep")
    if any(w in t for w in ("v9 max", "crew", "scanner", "agentes hermes", "roda o v9", "corre o max")):
        actions.append("run_v9_max")
    if "swarm" in t:
        actions.append("run_swarm")
    if any(w in t for w in ("supervisor", "ciclo hermes", "roda o supervisor")):
        actions.append("run_supervisor")

    # --- 404 / matriz ---
    if any(w in t for w in ("404", "matriz", "homepage", "aura.local", "pagina nao abre", "site nao abre")):
        actions.append("fix_desktop_json")

    # --- status ---
    if any(w in t for w in (
        "status", "estado", "como esta", "ta a funcionar", "esta online", "portas",
        "saude", "health", "o que esta a correr"
    )):
        actions.append("status")

    # --- relatorios ---
    if any(w in t for w in ("ultimo relatorio", "latest", "mostra o report", "ver log", "ver relatorio")):
        actions.append("latest")

    # --- leitura de ficheiro ---
    m = re.search(r"(?:le|ler|mostra|abre|open|cat|read)\s+(?:o\s+)?(?:ficheiro\s+|arquivo\s+|file\s+)?([^\s]+\.\w+)", t)
    if m:
        meta["read_path"] = m.group(1).strip("\"'`")
    m2 = re.search(r"(?:conteudo de|conteúdo de)\s+([^\s]+)", t)
    if m2 and "read_path" not in meta:
        meta["read_path"] = m2.group(1).strip("\"'`")

    # --- listar pasta ---
    m = re.search(r"(?:lista|listar|dir|ls)\s+(?:a\s+)?(?:pasta\s+|dir\s+|folder\s+)?([^\s]+)", t)
    if m:
        meta["list_path"] = m.group(1).strip("\"'`")
    if any(w in t for w in ("lista a raiz", "lista root", "o que tem na pasta", "estrutura")) and "list_path" not in meta:
        meta["list_path"] = "."

    # --- escrita ---
    if any(w in t for w in ("grava", "escreve", "salva", "write", "atualiza o ficheiro")):
        meta["want_write"] = True

    auto = bool(actions) or bool(meta)
    # Se o utilizador so descreveu o problema sem verbo de acao, ainda assim executamos
    if actions and not any(w in t for w in ("nao facas", "não faças", "so diz", "só diz", "apenas lista")):
        meta["auto"] = True

    return {"actions": actions, "blocked": False, "meta": meta, "reason": "ok"}


def _human_status_reply(st: Dict[str, Any]) -> str:
    ports = st.get("ports") or {}
    up = [k for k, v in ports.items() if v]
    down = [k for k, v in ports.items() if not v]
    live = st.get("live") or {}
    lines = ["Estado do AURA agora:"]
    if up:
        lines.append("  Online: " + ", ".join(up))
    if down:
        lines.append("  Offline: " + ", ".join(down))
    if live.get("exists"):
        if live.get("mode") == "paper_demo":
            lines.append(f"  Live: demo ({live.get('home')} vs {live.get('away')}) — aguarda captura real.")
        else:
            lines.append(f"  Live: {live.get('home')} vs {live.get('away')} | corners={live.get('corners')} | {live.get('status')}")
    else:
        lines.append("  Live: sem live_latest.json")
    lines.append("  Modo: paper_trade (sem apostas reais).")
    return "\n".join(lines)


def _human_action_reply(code: str, result: Dict[str, Any]) -> str:
    ok = result.get("ok")
    if code == "domain_lock":
        return "Domain lock aplicado. Hermes fica so em futebol/escanteios." if ok else f"Falhou domain lock: {result.get('error')}"
    if code == "fix_desktop_json":
        return "Homepage da Matriz apontada para http://127.0.0.1:8766." if ok else f"Falhou fix desktop: {result.get('error')}"
    if code == "train_v9":
        out = (result.get("stdout") or "")[-400:]
        return f"Treino V9 concluido.\n{out}" if ok else f"Treino falhou: {result.get('error') or result.get('stderr')}"
    if code == "run_v9_max":
        out = (result.get("stdout") or "")[-500:]
        return f"Crew V9 MAX:\n{out}" if ok else f"V9 MAX falhou: {result.get('error') or result.get('stderr')}"
    if code == "run_swarm":
        out = (result.get("stdout") or "")[-400:]
        return f"Swarm:\n{out}" if ok else f"Swarm falhou: {result.get('error')}"
    if code == "run_deep":
        out = (result.get("stdout") or "")[-500:]
        return f"Diagnostico profundo:\n{out}" if ok else f"Deep falhou: {result.get('error')}"
    if code == "run_supervisor":
        return "Supervisor executado." if ok else f"Supervisor falhou: {result.get('error')}"
    if code == "full_stack":
        return "Capacidade total aplicada (domain + desktop + treino + V9 + swarm + deep)." if ok else "Full stack com falhas parciais — ve detalhes nas acoes."
    if code == "status":
        return _human_status_reply(result)
    if code == "latest":
        reps = (result.get("reports") or {})
        bits = []
        for k, v in reps.items():
            if v:
                bits.append(f"--- {k} ---\n{v[:600]}")
        return "\n\n".join(bits) if bits else "Ainda nao ha relatorios em logs_supervisor."
    return f"{code}: {'ok' if ok else result.get('error')}"


def chat_reply(message: str) -> Dict[str, Any]:
    message = (message or "").strip()
    if not message:
        return {
            "reply": "Diz o que precisas. Exemplos: \"como esta o sistema\", \"arruma a matriz\", \"corre o diagnostico\", \"le o live_latest\", \"treina o hermes\".",
            "actions": [],
        }

    intent = interpret_intent(message)
    if intent.get("blocked"):
        return {
            "reply": "Nao. Este sistema e paper-trade apenas. Nao liberto execution_allowed nem apostas reais.",
            "actions": [],
            "blocked": True,
            "invariants": {"paper_trade": "true", "execution_allowed": "false"},
        }

    applied: List[Dict[str, Any]] = []
    parts: List[str] = []
    meta = intent.get("meta") or {}

    # Auto-executar acoes quando o desejo e claro
    for code in intent.get("actions") or []:
        result = apply_correction(code)
        applied.append({"code": code, "result": result})
        parts.append(_human_action_reply(code, result))

    # Leitura de ficheiro
    if meta.get("read_path"):
        r = _read_file_safe(meta["read_path"])
        if r.get("ok"):
            parts.append(f"Conteudo de {r['path']}:\n{r['content'][:3000]}")
            if r.get("truncated"):
                parts.append("(truncado)")
        else:
            parts.append(f"Nao consegui ler: {r.get('error')}")
        applied.append({"code": "fs_read", "result": r})

    # Listagem
    if meta.get("list_path") is not None:
        r = _list_dir_safe(meta.get("list_path") or ".")
        if r.get("ok"):
            lines = [f"Pasta {r['path']}:"]
            for it in r.get("items") or []:
                mark = "/" if it["type"] == "dir" else ""
                sz = f"  ({it['size']} B)" if it.get("size") is not None else ""
                lines.append(f"  {it['name']}{mark}{sz}")
            parts.append("\n".join(lines))
        else:
            parts.append(f"Nao listei: {r.get('error')}")
        applied.append({"code": "fs_list", "result": r})

    # Ollama opcional para tom natural quando nao houve acao estruturada
    llm_note = ""
    if not parts:
        ctx_bits = []
        logdir = ROOT / "logs_supervisor"
        for _name in ("HERMES_V9_MAX_LATEST.txt", "HERMES_DEEP_LATEST.txt"):
            _p = logdir / _name
            if _p.exists():
                try:
                    ctx_bits.append(_p.read_text(encoding="utf-8", errors="replace")[:600])
                except Exception:
                    pass
        _ctx = "\n".join(ctx_bits)[:1800]
        try:
            import urllib.request
            body = json.dumps({
                "model": "llama3.2:3b",
                "prompt": (
                    "Es o Hermes V9, operador do sistema AURA QUANT-X. "
                    "Papel: diagnostico, correcoes, status de servicos, logs, configs, captura. "
                    "Responde em PT-BR, curto, direto e humano. "
                    "paper_trade=true; NUNCA apostas reais nem execution_allowed=true. "
                    "Nao forces o utilizador a falar so de futebol — o chat e de operacao do sistema. "
                    "Contexto recente:\n" + _ctx + "\n\nUtilizador: " + message[:700] +
                    "\n\nResposta (sem enrolar):"
                ),
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:11434/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                llm_note = (data.get("response") or "").strip()[:900]
        except Exception:
            llm_note = ""

        if llm_note:
            parts.append(llm_note)
        else:
            # Fallback humano sem LLM
            parts.append(
                "Percebi. Sou o operador do AURA — diagnostico e correcoes. "
                "Exemplos: status, porque a bridge esta down, corre diagnostico, "
                "arruma o 404, le logs_supervisor, lista engine/data, full_stack."
            )

    reply = "\n\n".join(parts).strip()
    return {
        "reply": reply,
        "actions": applied,
        "suggested": intent.get("actions") or [],
        "blocked": False,
        "invariants": {"paper_trade": "true", "execution_allowed": "false"},
        "version": VERSION,
    }


CHAT_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Hermes V9 Chat</title>
<style>
  :root { --bg:#0b0f16; --card:#121826; --acc:#3b82f6; --txt:#e5e7eb; --mut:#9ca3af; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, sans-serif; background:var(--bg); color:var(--txt); }
  header { padding:12px 16px; border-bottom:1px solid #1f2937; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  header b { color:var(--acc); }
  #log { height: calc(100vh - 140px); overflow:auto; padding:16px; }
  .msg { max-width:760px; margin:0 auto 12px; padding:12px 14px; border-radius:12px; line-height:1.45; white-space:pre-wrap; word-break:break-word; }
  .user { background:#1e3a5f; }
  .bot { background:var(--card); border:1px solid #1f2937; }
  .mut { color:var(--mut); font-size:12px; }
  form { display:flex; gap:8px; padding:12px 16px; border-top:1px solid #1f2937; max-width:840px; margin:0 auto; }
  input { flex:1; padding:12px 14px; border-radius:10px; border:1px solid #374151; background:#0f172a; color:var(--txt); font-size:15px; }
  button { padding:12px 18px; border:0; border-radius:10px; background:var(--acc); color:white; font-weight:600; cursor:pointer; }
  button:hover { filter:brightness(1.08); }
</style>
</head>
<body>
<header>
  <b>Hermes</b>
  <span class="mut">operador AURA · diagnostico e correcoes · paper-safe · :8777</span>
</header>
<div id="log"></div>
<form id="f">
  <input id="q" placeholder="Ex: como esta o sistema · bridge down · arruma 404 · corre diagnostico · mostra logs" autocomplete="off"/>
  <button type="submit">Enviar</button>
</form>
<script>
const log = document.getElementById('log');
function add(cls, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
}
add('bot', 'Hermes V9 — operador AURA. Diagnostico, correcoes e status do sistema.\\nExemplos: \"como esta o sistema\", \"porque a bridge esta down\", \"arruma o 404\", \"corre diagnostico\", \"le os logs\".');
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const q = document.getElementById('q');
  const msg = q.value.trim();
  if (!msg) return;
  add('user', msg);
  q.value = '';
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const j = await r.json();
    add('bot', j.reply || JSON.stringify(j));
  } catch (err) {
    add('bot', 'Erro de ligacao: ' + err);
  }
};
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[hermes-v9-api] " + (fmt % args) + "\n")

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, code: int, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace") or "{}")
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/chat", "/ui"):
            self._html(200, CHAT_HTML)
            return
        if path == "/health":
            self._json(200, {
                "ok": True,
                "version": VERSION,
                "root": str(ROOT),
                "paper_trade": True,
                "execution_allowed": False,
            })
            return
        if path == "/api/allowlist":
            self._json(200, {k: v["desc"] for k, v in ALLOWLIST.items()})
            return
        if path == "/api/policy":
            pol = ROOT / "engine" / "data" / "hermes_v9_trained_policy.json"
            if pol.exists():
                try:
                    self._json(200, json.loads(pol.read_text(encoding="utf-8")))
                    return
                except Exception as e:
                    self._json(500, {"error": str(e)})
                    return
            self._json(404, {"error": "policy_absent"})
            return
        if path == "/api/latest":
            self._json(200, _latest_reports())
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/chat":
                msg = body.get("message") or body.get("prompt") or body.get("text") or ""
                self._json(200, chat_reply(str(msg)))
                return
            if path == "/api/prompt":
                self._json(200, interpret_intent(str(body.get("prompt") or body.get("message") or "")))
                return
            if path == "/api/correct":
                code = str(body.get("code") or "").strip()
                self._json(200, apply_correction(code))
                return
            if path == "/api/cycle":
                self._json(200, apply_correction("run_v9_max"))
                return
            if path == "/api/fs/read":
                self._json(200, _read_file_safe(str(body.get("path") or "")))
                return
            if path == "/api/fs/list":
                self._json(200, _list_dir_safe(str(body.get("path") or ".")))
                return
            if path == "/api/fs/write":
                self._json(200, _write_file_safe(str(body.get("path") or ""), str(body.get("content") or "")))
                return
            self._json(404, {"error": "not_found"})
        except Exception as e:
            self._json(500, {"error": str(e), "trace": traceback.format_exc()[-800:]})


def main() -> None:
    host = os.environ.get("HERMES_API_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, PORT), Handler)
    print(f"{VERSION} listening on http://{host}:{PORT}  ROOT={ROOT}", flush=True)
    print("invariants: paper_trade=true execution_allowed=false", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutdown", flush=True)


if __name__ == "__main__":
    main()
