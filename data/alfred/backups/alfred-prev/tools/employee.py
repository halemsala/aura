"""Modo funcionário + criativos: focus, Photoshop, pesquisa de skills."""
from .. import focus_mode
from ..registry import ToolSpec, register
from ..validators import ValidationError
from . import apps, skills_search


def _v0(args) -> dict:
    return {}


def alfred_focus_on(args, ctx) -> dict:
    reason = str((args or {}).get("reason") or "trabalho fora do Aura")[:200]
    if ctx.dry():
        return {"dry_run": True, "would_pause": list(focus_mode.PAUSABLE.values()),
                "protected": sorted(focus_mode.PROTECTED_PORTS),
                "nota": "NADA parado. AUTORIZO para pausar bridge/engine/matriz/voz e libertar GPU ao Alfred."}
    return focus_mode.enter(reason)


def alfred_focus_off(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "não saio do modo funcionário em dry-run"}
    return focus_mode.exit_focus()


def alfred_focus_status(args, ctx) -> dict:
    return focus_mode.status()


register(ToolSpec("alfred_focus_on", alfred_focus_on, _v0, risk="high", mutating=True,
                  summary="Pausa agentes extra (bridge/engine/matriz/voz). Nunca mata Ollama/Hermes/Alfred."))
register(ToolSpec("alfred_focus_off", alfred_focus_off, _v0, risk="medium", mutating=True,
                  summary="Sai do modo funcionário e reativa o watchdog (sem auto-reparo)."))
register(ToolSpec("alfred_focus_status", alfred_focus_status, _v0, risk="low", mutating=False,
                  summary="Estado do modo funcionário"))


def _v_creative(args) -> dict:
    brief = str((args or {}).get("brief") or (args or {}).get("text") or "").strip()
    if not brief:
        raise ValidationError("indica o brief do criativo")
    return {"brief": brief[:500]}


def create_creative_plan(args, ctx) -> dict:
    """Plano só: não abre Photoshop sozinho neste passo se dry."""
    a = _v_creative(args)
    skills = skills_search.search_skill({"query": a["brief"]}, ctx)
    apps_found = apps.list_apps({}, ctx)
    ps = next((x for x in apps_found["apps"] if x["app"] == "photoshop"), {})
    return {
        "brief": a["brief"],
        "photoshop_installed": bool(ps.get("installed")),
        "skills": skills.get("local_skills"),
        "learn_urls": skills.get("suggested_urls"),
        "proposed_files": ["Desktop/Creativos/"],
        "next": [
            "alfred_focus_on (libertar GPU)",
            "open_app photoshop" if ps.get("installed") else "Photoshop não encontrado — instalar ou usar paint",
            "search_skill + abrir URL só se pedires",
            "guardar em Desktop/Creativos com AUTORIZO",
        ],
        "nota": "nenhuma app aberta e nenhum ficheiro escrito neste passo. AUTORIZO as tarefas mutáveis uma a uma.",
    }


register(ToolSpec("create_creative_plan", create_creative_plan, _v_creative, risk="low", mutating=False,
                  summary="Monta o plano de um criativo (skills + Photoshop) sem executar"))
