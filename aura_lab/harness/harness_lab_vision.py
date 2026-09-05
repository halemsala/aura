#!/usr/bin/env python3
"""
AURA Harness — LAB + Visão ampliada (overlay).

Como usar:
  1) Coloque aura_lab ao lado do harness OU defina AURA_LAB_ROOT.
  2) No FINAL do AURA_HARNESS_UNICO_CONSOLIDADO.py (antes do if __name__),
     adicione:

       from harness_lab_vision import apply_lab_vision
       apply_lab_vision(globals())

  Ou execute este arquivo depois de importar o harness (mesmo processo).

Efeitos:
  - intent: lab diagnostico / visão / panorama / o que voce ve
  - collect_snapshot expandido (ui/state, voice detail, starters, staging, lab)
  - help atualizado
  - status mais completo
  - lab_diagnose integrado (advisory, grava jsonl)

Não remove travas: paper_trade, CONFIRMAR, execution_allowed=false.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Localização do LAB
# ---------------------------------------------------------------------------

def _discover_lab_root() -> Path | None:
    env = os.environ.get("AURA_LAB_ROOT")
    if env:
        p = Path(env)
        if (p / "catalog" / "failure_modes_v1.yaml").is_file():
            return p
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent,  # aura_lab/harness -> aura_lab
        Path.cwd() / "aura_lab",
        Path.cwd(),
        Path(__file__).resolve().parents[2] / "aura_lab",
    ]
    for c in candidates:
        if (c / "catalog" / "failure_modes_v1.yaml").is_file():
            return c
        if (c / "aura_lab" / "catalog" / "failure_modes_v1.yaml").is_file():
            return c / "aura_lab"
    return None


LAB_ROOT = _discover_lab_root()


def _http_get(url: str, timeout: float = 1.6) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data: Any = json.loads(raw)
            except json.JSONDecodeError:
                data = raw[:500]
            return {
                "online": True,
                "status": getattr(resp, "status", 200),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "data": data,
            }
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def _safe_keys(obj: Any, limit: int = 30) -> list[str]:
    if isinstance(obj, dict):
        return list(obj.keys())[:limit]
    return []


def _read_log_tail(path: Path, max_chars: int = 1800) -> dict[str, Any]:
    """Lê o final de um log oficial (só leitura). Tolerante a ausência/encoding."""
    try:
        if not path.is_file():
            return {"exists": False, "path": str(path)}
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            handle.seek(max(0, end - max_chars * 4))
            data = handle.read()
        text = data.decode("utf-8", errors="replace")[-max_chars:]
        # últimas linhas não vazias
        lines = [ln for ln in text.splitlines() if ln.strip()]
        tail_lines = lines[-12:] if lines else []
        return {
            "exists": True,
            "path": str(path),
            "size_bytes": size,
            "tail": "\n".join(tail_lines),
            "tail_lines": len(tail_lines),
        }
    except OSError as exc:
        return {"exists": False, "path": str(path), "error": str(exc)}


def _summarize_deep(data: Any) -> dict[str, Any]:
    """Resume /api/diagnostics/deep sem despejar o JSON inteiro no chat."""
    if not isinstance(data, dict):
        return {"type": type(data).__name__, "preview": str(data)[:200]}
    summary: dict[str, Any] = {"keys": _safe_keys(data, 40)}
    # campos comuns em builds AURA
    for key in (
        "ok",
        "status",
        "paper_trade",
        "execution_allowed",
        "errors",
        "warnings",
        "services",
        "gpu",
        "ollama",
        "capture",
        "freshness",
        "risk",
        "data_integrity",
    ):
        if key in data:
            val = data[key]
            if isinstance(val, (str, int, float, bool)) or val is None:
                summary[key] = val
            elif isinstance(val, list):
                summary[key] = val[:8]
            elif isinstance(val, dict):
                summary[key] = {k: val[k] for k in list(val.keys())[:12]}
    # erros aninhados curtos
    err = data.get("error") or data.get("last_error")
    if err:
        summary["error"] = str(err)[:300]
    return summary


def expand_snapshot(base: dict[str, Any], aura_root: Path) -> dict[str, Any]:
    """Enriquece snapshot existente — só leitura."""
    vision: dict[str, Any] = {
        "vision_version": "1.1",
        "lab_root": str(LAB_ROOT) if LAB_ROOT else None,
        "layers": {},
    }

    services = base.get("services") or {}

    # Engine: ui/state + status
    eng = services.get("engine") or {}
    if eng.get("online"):
        ui = _http_get("http://127.0.0.1:8765/api/ui/state")
        vision["layers"]["ui_state"] = {
            "reachable": bool(ui.get("online")),
            "keys": _safe_keys(ui.get("data")) if ui.get("online") else [],
            "error": ui.get("error"),
        }
        st = _http_get("http://127.0.0.1:8765/api/status")
        if st.get("online") and isinstance(st.get("data"), dict):
            data = st["data"]
            vision["layers"]["engine_status"] = {
                "keys": _safe_keys(data),
                "paper_trade": data.get("paper_trade", data.get("policy", {}).get("paper_trade") if isinstance(data.get("policy"), dict) else None),
                "latency_ms": st.get("latency_ms"),
            }
        else:
            vision["layers"]["engine_status"] = {"reachable": bool(st.get("online")), "error": st.get("error")}
        # diagnostics deep (vários paths usados em builds)
        deep = None
        for path in (
            "/api/diagnostics/deep",
            "/api/diagnostic/deep",
            "/api/diagnostics",
        ):
            deep = _http_get(f"http://127.0.0.1:8765{path}", timeout=2.2)
            if deep.get("online"):
                vision["layers"]["diagnostics_deep"] = {
                    "reachable": True,
                    "path": path,
                    "latency_ms": deep.get("latency_ms"),
                    "summary": _summarize_deep(deep.get("data")),
                }
                break
        if not vision["layers"].get("diagnostics_deep"):
            vision["layers"]["diagnostics_deep"] = {
                "reachable": False,
                "error": (deep or {}).get("error") or "endpoint_indisponivel",
            }
    else:
        vision["layers"]["ui_state"] = {"reachable": False, "reason": "engine_offline"}
        vision["layers"]["engine_status"] = {"reachable": False}
        vision["layers"]["diagnostics_deep"] = {"reachable": False, "reason": "engine_offline"}

    # Voice detail
    voice = services.get("voice") or {}
    if voice.get("online"):
        vh = voice.get("health") or _http_get("http://127.0.0.1:8099/api/voice/health")
        data = vh.get("data") if isinstance(vh, dict) else None
        if isinstance(data, dict):
            vision["layers"]["voice"] = {
                "reachable": True,
                "loading": data.get("loading"),
                "device": data.get("device"),
                "engineReady": data.get("engineReady"),
                "llmModel": data.get("llmModel") or (data.get("llmHealth") or {}).get("active_model"),
                "error": data.get("error") or (data.get("llmHealth") or {}).get("last_error"),
            }
        else:
            vision["layers"]["voice"] = {"reachable": True, "raw": bool(vh)}
    else:
        vision["layers"]["voice"] = {"reachable": False}

    # Disco: pastas oficiais
    root = Path(aura_root)
    disk = {}
    for name in ("engine", "bridge", "extensao", "scripts", "desktop", "state", "halem_control"):
        p = root / name
        disk[name] = p.is_dir()
    vision["layers"]["disk"] = disk
    vision["layers"]["aura_root"] = str(root)

    # Starters conhecidos (existência em disco — nomes comuns)
    starters = {}
    for label, paths in {
        "master": ["INSTALAR_E_INICIAR_TUDO.bat", "AURA_INICIAR_SISTEMA.bat", "AURA_INSTALAR_E_INICIAR_TUDO.bat"],
        "engine": ["iniciar_engine.bat", "start_engine.bat"],
        "voice": ["iniciar_voz.bat", "bridge/iniciar_voz.bat"],
        "recover": ["RECUPERAR_AURA_SERVICOS.bat", "RECUPERAR_AURA_SERVICOS.ps1"],
        "diag": ["DIAGNOSTICO_AURA.bat", "DIAGNOSTICO_WINDOWS_COMPLETO.bat"],
    }.items():
        found = None
        for rel in paths:
            cand = root / rel
            if cand.is_file():
                found = str(cand)
                break
        starters[label] = found
    vision["layers"]["starters"] = starters

    # Staging / skills se CONTROL paths existirem no host
    control = root / "halem_control"
    vision["layers"]["control"] = {
        "exists": control.is_dir(),
        "staging": (control / "staging").is_dir(),
        "audit": (control / "audit.jsonl").is_file(),
    }

    # LAB
    if LAB_ROOT:
        cat = LAB_ROOT / "catalog" / "failure_modes_v1.yaml"
        vision["layers"]["lab"] = {
            "available": True,
            "catalog": str(cat) if cat.is_file() else None,
            "records": str(LAB_ROOT / "records" / "lab_failures.jsonl"),
        }
    else:
        vision["layers"]["lab"] = {"available": False}

    # Logs oficiais (tail) — só leitura
    log_specs = [
        ("engine", root / "engine" / "runtime_engine.log"),
        ("bridge", root / "bridge" / "runtime_bridge.log"),
        ("voice", root / "bridge" / "runtime_voice.log"),
        ("install", root / "install_run.log"),
        ("recovery", root / "recovery_services.log"),
    ]
    # variantes comuns
    extra_candidates = {
        "engine": [root / "engine" / "logs" / "runtime_engine.log", root / "logs" / "runtime_engine.log"],
        "bridge": [root / "bridge" / "logs" / "runtime_bridge.log"],
        "voice": [root / "bridge" / "logs" / "runtime_voice.log", root / "voice" / "runtime_voice.log"],
    }
    logs: dict[str, Any] = {}
    for label, primary in log_specs:
        info = _read_log_tail(primary)
        if not info.get("exists"):
            for alt in extra_candidates.get(label, []):
                alt_info = _read_log_tail(alt)
                if alt_info.get("exists"):
                    info = alt_info
                    break
        logs[label] = info
    vision["layers"]["logs"] = logs

    # Cobertura estimada (heurística honesta para o operador)
    log_any = any(v.get("exists") for v in logs.values())
    deep_ok = bool((vision["layers"].get("diagnostics_deep") or {}).get("reachable"))
    checks = [
        any((services.get(s) or {}).get("online") for s in services),
        vision["layers"].get("ui_state", {}).get("reachable"),
        vision["layers"].get("voice", {}).get("reachable") or not (services.get("voice") or {}).get("online"),
        any(disk.values()),
        any(starters.values()),
        vision["layers"]["lab"].get("available"),
        log_any,
        deep_ok or not (services.get("engine") or {}).get("online"),
    ]
    vision["coverage_score_approx"] = round(100 * sum(1 for c in checks if c) / max(len(checks), 1))

    base = dict(base)
    base["vision"] = vision
    return base


def format_vision_report(snapshot: dict[str, Any]) -> str:
    lines = ["══ AURA — visão ampliada do sistema (só leitura) ══"]
    services = snapshot.get("services") or {}
    for name, item in services.items():
        st = "ONLINE" if item.get("online") else "OFFLINE"
        lat = (item.get("health") or {}).get("latency_ms", "-")
        lines.append(f"  {name:8} {st:7} porta={item.get('port')} lat={lat}")
    vis = snapshot.get("vision") or {}
    layers = vis.get("layers") or {}
    lines.append("")
    lines.append(f"AURA_ROOT: {layers.get('aura_root', '?')}")
    disk = layers.get("disk") or {}
    if disk:
        missing = [k for k, ok in disk.items() if not ok]
        lines.append("Pastas: " + ", ".join(f"{k}{'✓' if ok else '✗'}" for k, ok in disk.items()))
        if missing:
            lines.append(f"  Faltando no disco: {', '.join(missing)}")
    ui = layers.get("ui_state") or {}
    lines.append(f"UI state: {'ok keys=' + str(ui.get('keys')) if ui.get('reachable') else 'indisponível (' + str(ui.get('reason') or ui.get('error') or '') + ')'}")
    voice = layers.get("voice") or {}
    if voice.get("reachable"):
        lines.append(
            f"Voice: device={voice.get('device')} ready={voice.get('engineReady')} "
            f"model={voice.get('llmModel')} err={voice.get('error')}"
        )
    else:
        lines.append("Voice: offline")
    starters = layers.get("starters") or {}
    lines.append("Starters oficiais:")
    for k, v in starters.items():
        lines.append(f"  · {k}: {v or 'não encontrado'}")
    lab = layers.get("lab") or {}
    lines.append(f"LAB: {'disponível em ' + str(lab.get('catalog')) if lab.get('available') else 'não encontrado (defina AURA_LAB_ROOT)'}")

    deep = layers.get("diagnostics_deep") or {}
    if deep.get("reachable"):
        summ = deep.get("summary") or {}
        lines.append(f"Diagnostics deep: OK via {deep.get('path')} ({deep.get('latency_ms')}ms)")
        if summ.get("keys"):
            lines.append(f"  keys: {summ.get('keys')[:15]}")
        for k in ("paper_trade", "execution_allowed", "status", "ok", "error"):
            if k in summ:
                lines.append(f"  {k}: {summ.get(k)}")
        for k in ("errors", "warnings"):
            if summ.get(k):
                lines.append(f"  {k}: {summ.get(k)}")
    else:
        lines.append(
            f"Diagnostics deep: indisponível ({deep.get('reason') or deep.get('error') or 'n/d'})"
        )

    logs = layers.get("logs") or {}
    if logs:
        lines.append("Logs oficiais (tail):")
        for name, info in logs.items():
            if info.get("exists"):
                lines.append(f"  · {name}: {info.get('path')} ({info.get('size_bytes')} bytes)")
                tail = (info.get("tail") or "").strip()
                if tail:
                    for ln in tail.splitlines()[-4:]:
                        lines.append(f"      | {ln[:160]}")
            else:
                err = info.get("error")
                lines.append(f"  · {name}: ausente" + (f" ({err})" if err else ""))

    lines.append(f"Cobertura aproximada desta visão: {vis.get('coverage_score_approx', '?')}%")
    pol = snapshot.get("policy") or {}
    lines.append(
        f"Policy: paper_trade={pol.get('paper_trade')} execution_allowed={pol.get('execution_allowed')} "
        f"modo={pol.get('mode')}"
    )
    lines.append("")
    lines.append("Isto é observabilidade do AURA — não operação autônoma do Windows inteiro.")
    lines.append("Comandos: status · visão · lab diagnostico <sintoma> · ajuda")
    return "\n".join(lines)


def run_lab_diagnose(symptom: str, with_snapshot: bool = True) -> str:
    if not LAB_ROOT:
        return (
            "❌ AURA LAB não encontrado.\n"
            "Coloque a pasta aura_lab acessível ou defina AURA_LAB_ROOT.\n"
            "Pacote: AURA_LAB_v*.zip"
        )
    tools = LAB_ROOT / "tools"
    import sys

    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        from lab_diagnose import (  # type: ignore
            build_query,
            format_report,
            match_symptom,
            load_yaml,
            validate_catalog,
        )
        from catalog_loader import load_yaml as _ly  # noqa: F401
        from record_writer import append_record
        from snapshot import collect_snapshot as lab_snap, offline_services
    except Exception as exc:
        return f"❌ Falha ao importar ferramentas LAB: {exc}"

    cat = LAB_ROOT / "catalog" / "failure_modes_v1.yaml"
    data = load_yaml(cat)
    modes, errors = validate_catalog(data)
    if errors:
        return "Catálogo LAB inválido:\n" + "\n".join(errors)

    snap = lab_snap() if with_snapshot else None
    query = build_query(symptom or "", snap)
    hits = match_symptom(modes, query, limit=5)
    report = format_report(symptom or query, snap, hits)
    best = hits[0][1] if hits else None
    observed: dict[str, Any] = {"symptom_text": symptom or query}
    if snap:
        observed["offline"] = offline_services(snap)
        observed["services"] = {
            k: {"online": v.get("online"), "port": v.get("port")}
            for k, v in (snap.get("services") or {}).items()
        }
    rec = append_record(
        LAB_ROOT / "records" / "lab_failures.jsonl",
        failure_mode_id=(best or {}).get("id") or "FM-UNKNOWN-000",
        phase="diagnosed" if best else "detected",
        observed=observed,
        diagnosis=(best or {}).get("title"),
        proposed_repair=list((best or {}).get("repair_steps") or []),
        notes="harness lab diagnostico",
        operator="harness",
    )
    return report + f"\nRegistro LAB: {rec.get('record_id')}"


def apply_lab_vision(ns: dict[str, Any] | None = None) -> str:
    """Aplica monkey-patch no namespace do harness (globals do módulo principal)."""
    if ns is None:
        import sys

        # tenta módulo __main__
        ns = vars(sys.modules.get("__main__", sys.modules[__name__]))

    Halem = ns.get("Halem")
    collect_snapshot = ns.get("collect_snapshot")
    show_status = ns.get("show_status")
    AURA_ROOT = ns.get("AURA_ROOT")
    if Halem is None or collect_snapshot is None:
        return "❌ apply_lab_vision: Halem/collect_snapshot não encontrados no namespace"

    _orig_collect = collect_snapshot
    _orig_intent = Halem.intent
    _orig_handle = Halem.handle
    _orig_help = Halem.help
    _orig_show = show_status

    def collect_snapshot_v2():
        base = _orig_collect()
        root = Path(AURA_ROOT) if AURA_ROOT is not None else Path(r"C:\aura")
        return expand_snapshot(base, root)

    ns["collect_snapshot"] = collect_snapshot_v2

    def show_status_v2(snapshot: dict) -> None:
        _orig_show(snapshot)
        try:
            text = format_vision_report(snapshot)
            out = ns.get("out")
            if callable(out):
                out(text)
            else:
                print(text)
        except Exception as exc:
            print(f"(visão ampliada indisponível: {exc})")

    ns["show_status"] = show_status_v2

    def intent_v2(self, raw: str):
        text = ns["normalize"](raw)
        # LAB
        if text in {"lab", "aura lab", "ferramenta lab"}:
            return "lab_help", None
        if text.startswith("lab diagnostico") or text.startswith("lab diagnosticar"):
            rest = re.sub(r"^lab\s+diagnostic[oa]r?\s*", "", text, count=1).strip()
            return "lab_diagnose", rest
        if text.startswith("diagnostico lab") or text.startswith("diagnóstico lab"):
            rest = re.sub(r"^diagn[oó]stico\s+lab\s*", "", text, count=1).strip()
            return "lab_diagnose", rest
        if any(
            p in text
            for p in (
                "lab diagnostico",
                "lab diagnose",
                "rodar lab",
                "usar o lab",
                "failure mode",
            )
        ):
            # "lab diagnostico engine offline"
            m = re.search(r"lab\s+diagnostic[oa]r?\s+(.+)", text)
            if m:
                return "lab_diagnose", m.group(1).strip()
            return "lab_help", None
        # Visão
        if text in {
            "visao",
            "visão",
            "visao completa",
            "visão completa",
            "panorama",
            "o que voce ve",
            "o que você vê",
            "o que voce enxerga",
            "o que você enxerga",
            "cobertura",
            "visao do sistema",
            "visão do sistema",
        }:
            return "vision", None
        # OPS LOOP
        if text in {
            "ops",
            "ops loop",
            "loop operacional",
            "recuperar sugestao",
            "recuperar sugestão",
            "detectar falhas",
            "auto diagnostico",
            "autodiagnostico",
            "auto diagnóstico",
        } or text.startswith("ops ") or text.startswith("ops loop"):
            rest = re.sub(r"^(ops\s+loop|ops|loop operacional)\s*", "", text).strip()
            return "ops_loop", rest
        if text in {"painel", "vision panel", "painel visao", "painel visão", "abrir painel"}:
            return "vision_panel", None
        if text in {
            "experiencias",
            "experiências",
            "o que aprendemos",
            "memoria lab",
            "memória lab",
            "historico lab",
            "histórico lab",
        }:
            return "experiences", None
        if text in {"daemon", "ops daemon", "iniciar daemon", "como daemon"}:
            return "ops_daemon_help", None
        return _orig_intent(self, raw)

    def _run_ops_loop(symptom: str) -> str:
        if not LAB_ROOT:
            return "❌ AURA LAB não encontrado (AURA_LAB_ROOT)."
        tools = LAB_ROOT / "tools"
        import sys as _sys

        if str(tools) not in _sys.path:
            _sys.path.insert(0, str(tools))
        try:
            from ops_loop import run_loop, format_ops_report  # type: ignore
        except Exception as exc:
            return f"❌ ops_loop indisponível: {exc}"
        result = run_loop(symptom or "", record=True, wait_verify_s=0.0)
        return format_ops_report(result)

    async def handle_v2(self, raw: str):
        kind, value = self.intent(raw)
        if kind == "lab_help":
            return (
                "AURA LAB (advisory)\n"
                "· lab diagnostico <sintoma>  — match no catálogo + snapshot + registro\n"
                "· ops / ops loop [sintoma]   — detectar → FM → recovery → verificar\n"
                "· experiencias               — memória do que foi visto/resolvido\n"
                "· daemon                     — como rodar observação automática\n"
                "· visão / panorama · painel · status\n"
                "Auto-repair OFF. Nada muda sem CONFIRMAR. Paper trade ativo."
            )
        if kind == "lab_diagnose":
            symptom = (value or "").strip()
            return await asyncio.to_thread(run_lab_diagnose, symptom, True)
        if kind == "ops_loop":
            return await asyncio.to_thread(_run_ops_loop, (value or "").strip())
        if kind == "experiences":
            def _exp() -> str:
                if not LAB_ROOT:
                    return "❌ LAB não encontrado."
                tools = LAB_ROOT / "tools"
                import sys as _sys

                if str(tools) not in _sys.path:
                    _sys.path.insert(0, str(tools))
                from experiences import summarize_experiences  # type: ignore

                return summarize_experiences(limit=40)

            return await asyncio.to_thread(_exp)
        if kind == "ops_daemon_help":
            if not LAB_ROOT:
                return "❌ LAB não encontrado (AURA_LAB_ROOT)."
            daemon = LAB_ROOT / "tools" / "ops_daemon.py"
            return (
                "Observação automática (sem auto-repair):\n"
                f"  python \"{daemon}\" --once\n"
                f"  python \"{daemon}\" --interval 120\n"
                "Grava experiences.jsonl quando detecta problema.\n"
                "No Harness: experiencias · ops · lab diagnostico\n"
                "Agendador Windows: a cada 5–10 min --once é suficiente."
            )
        if kind == "vision_panel":
            if not LAB_ROOT:
                return "❌ LAB não encontrado — não dá para subir o painel."
            panel = LAB_ROOT / "tools" / "vision_panel.py"
            if not panel.is_file():
                return f"❌ vision_panel.py ausente em {panel}"
            # não bloqueia o chat: orienta o operador (Windows)
            return (
                "Painel de visão (só leitura):\n"
                f"  python \"{panel}\"\n"
                "Depois abra http://127.0.0.1:3029/\n"
                "Atualiza a cada 15s. Não executa recovery. Mutação = Harness + CONFIRMAR."
            )
        if kind == "vision":
            snapshot = await asyncio.to_thread(ns["collect_snapshot"])
            return format_vision_report(snapshot)
        if kind == "status":
            snapshot = await asyncio.to_thread(ns["collect_snapshot"])
            ns["show_status"](snapshot)
            # também devolve texto para o chat não ficar “mudo”
            return format_vision_report(snapshot)
        # delega o restante
        # re-bind: handle original usa self.intent já patchado
        return await _orig_handle(self, raw)

    def help_v2(self):
        base = _orig_help(self)
        extra = (
            "\n— Visão & LAB & OPS —\n"
            "visão / panorama · status (ampliado)\n"
            "lab diagnostico · ops · experiencias · daemon\n"
            "painel (UI local :3029)\n"
            "O Harness observa serviços, UI state, voz, starters e LAB.\n"
            "Não opera o Windows inteiro sozinho; mutação exige CONFIRMAR."
        )
        return base + extra

    Halem.intent = intent_v2
    Halem.handle = handle_v2
    Halem.help = help_v2
    ns["_lab_vision_applied"] = True
    return (
        f"✅ LAB+Visão aplicados. LAB_ROOT={LAB_ROOT} "
        f"(defina AURA_LAB_ROOT se vazio)"
    )


if __name__ == "__main__":
    print("Módulo harness_lab_vision — importe e chame apply_lab_vision(globals()) no harness.")
    print(f"LAB_ROOT={LAB_ROOT}")
