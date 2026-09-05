"""Reparo do Aura, paper_trade (sem apostas reais), voz, VRAM."""
from .. import flags, voice_win
from ..config import get_config, reset_config_cache
from ..registry import ToolSpec, register
from ..validators import ValidationError
from .. import autocorrect
from . import system_tools
from ..gpu_share import manager


def _v0(args) -> dict:
    return {}


def _v_flag(args) -> dict:
    args = args or {}
    name = str(args.get("flag") or "").strip()
    if name not in ("paper_trade", "system_repair_allowed", "voice_enabled", "observe_pc_enabled"):
        raise ValidationError("flag inválida")
    if "value" not in args:
        raise ValidationError("value true|false obrigatório")
    raw = args.get("value")
    val = raw is True or str(raw).lower() in ("1", "true", "yes", "on")
    if name == "paper_trade" and val is False:
        pass
    return {"flag": name, "value": val, "reason": str(args.get("reason") or "")[:200]}


def set_aura_flag(args, ctx) -> dict:
    a = _v_flag(args)
    if a["flag"] == "paper_trade" and a["value"] is False:
        note = ("paper_trade=false NÃO liga apostas reais: execution_allowed continua false. "
                "Serve para o Hermes deixar de tratar correcções do Aura como 'só paper'.")
    else:
        note = ""
    if ctx.dry():
        return {"dry_run": True, **a, "nota": "flags NÃO alteradas. AUTORIZO para gravar. " + note}
    data = flags.load_flags()
    data[a["flag"]] = a["value"]
    if a["flag"] == "paper_trade" and a["value"] is False:
        data["system_repair_allowed"] = True
    saved = flags.save_flags(data, reason=a["reason"] or f"set {a['flag']}={a['value']}")
    reset_config_cache()
    return {"saved": True, "flags": saved, "nota": note}


register(ToolSpec("set_aura_flag", set_aura_flag, _v_flag, risk="high", mutating=True,
                  summary="Altera paper_trade / system_repair / voz. execution_allowed nunca fica true."))


def repair_aura(args, ctx) -> dict:
    fl = flags.load_flags()
    if not fl.get("system_repair_allowed"):
        return {
            "blocked": True,
            "nota": "Reparos reais estão desligados. Diz: Alfred, desativa paper_trade  "
                    "ou Alfred, ativa reparo do sistema  e depois AUTORIZO.",
            "flags": fl,
        }
    return autocorrect.run_cycle(incident=str((args or {}).get("incident") or "repair-aura"),
                                 authorized=bool(ctx.authorized),
                                 hypothesis="reparo real do Aura autorizado pelo utilizador")


register(ToolSpec("repair_aura", repair_aura, _v0, risk="high", mutating=True,
                  summary="Reparo real do Aura (só com system_repair_allowed + AUTORIZO)"))


def speak_reply(args, ctx) -> dict:
    text = str((args or {}).get("text") or "").strip()
    if not text:
        raise ValidationError("text vazio")
    if ctx.dry():
        return {"dry_run": True, "would_speak": text[:80]}
    return voice_win.speak(text)


def listen_voice(args, ctx) -> dict:
    """Grava o microfone Windows (Realtek) e transcreve no Whisper :8099."""
    sec = int((args or {}).get("seconds") or 8)
    try:
        import requests
        r = requests.post(
            "http://127.0.0.1:8099/api/voice/listen",
            json={"seconds": sec, "prefer": "realtek"},
            timeout=90,
        )
        data = r.json() if r.content else {}
        data["http"] = r.status_code
        return data
    except Exception as exc:
        from alfred.mic_capture import record as _record
        rec = _record(seconds=sec, prefer="realtek")
        rec["ok"] = True
        rec["error"] = str(exc)[:180]
        rec["nota"] = "Gravei o microfone Windows mas o Whisper :8099 não respondeu."
        return rec


register(ToolSpec("speak_reply", speak_reply, lambda a: {"text": str((a or {}).get("text") or "")[:500]},
                  risk="low", mutating=False,
                  summary="Fala o texto com voz neural pt-BR (Humberto, pausas)"))
register(ToolSpec("listen_voice", listen_voice, _v0, risk="low", mutating=False,
                  summary="Escuta o microfone Realtek do Windows (não o browser) e transcreve com Whisper."))


def vram_capacity(args, ctx) -> dict:
    st = system_tools.system_status({}, ctx)
    gpu = st.get("gpu") or {}
    free = float(gpu.get("vram_free_mib") or 0)
    total = float(gpu.get("vram_total_mib") or 0)
    if free >= 2000:
        ctx_rec = 4096
    elif free >= 800:
        ctx_rec = 2048
    else:
        ctx_rec = 1024
    remote = []
    for w in manager.list_workers():
        remote.append(manager.worker_status(w["host"], w["port"], w.get("token") or ""))
    return {
        "local_gpu": gpu,
        "recommended_num_ctx": ctx_rec,
        "current_num_ctx": get_config().get("num_ctx"),
        "workers": remote,
        "ready_for_more_vram": True,
        "nota": "VRAM remota não entra nesta placa: workers correm o trabalho e devolvem o resultado. "
                "Quando houver mais VRAM local, sobe num_ctx (Alfred, adapta vram).",
    }


def adapt_vram(args, ctx) -> dict:
    plan = vram_capacity({}, ctx)
    if ctx.dry():
        return {"dry_run": True, "would_set_num_ctx": plan["recommended_num_ctx"], **plan}
    from .. import paths
    import json
    cfg_path = paths.CONFIG_PATH
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data["num_ctx"] = int(plan["recommended_num_ctx"])
    cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    from ..config import reset_config_cache
    reset_config_cache()
    return {"adapted": True, "num_ctx": data["num_ctx"], "gpu": plan.get("local_gpu")}


register(ToolSpec("vram_capacity", vram_capacity, _v0, risk="low", mutating=False,
                  summary="Capacidade local + workers GPU e num_ctx recomendado"))
register(ToolSpec("adapt_vram", adapt_vram, _v0, risk="medium", mutating=True,
                  summary="Ajusta num_ctx à VRAM livre (AUTORIZO). Pronto para mais VRAM."))
