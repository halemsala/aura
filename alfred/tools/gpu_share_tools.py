"""Ferramentas Alfred para o gestor de GPU partilhada."""
import ipaddress
import re

from ..gpu_share import manager
from ..registry import ToolSpec, register
from ..validators import ValidationError


def _v0(args) -> dict:
    return {}


def export_gpu_worker(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "não crio o ZIP sem AUTORIZO"}
    return manager.export_pack()


register(ToolSpec("export_gpu_worker", export_gpu_worker, _v0, risk="low", mutating=True,
                  summary="Gera ZIP AURA_GPU_WORKER para copiar para outro PC (não abre browser, não abre LAN)"))


def list_gpu_workers(args, ctx) -> dict:
    items = []
    for w in manager.list_workers():
        items.append({"host": w.get("host"), "port": w.get("port"), "label": w.get("label")})
    return {"workers": items}


register(ToolSpec("list_gpu_workers", list_gpu_workers, _v0, risk="low", mutating=False,
                  summary="Lista workers GPU registados (sem mostrar tokens)"))


def _v_reg(args) -> dict:
    args = args or {}
    host = str(args.get("host") or "").strip()
    port = int(args.get("port") or 8795)
    if port < 8795 or port > 8799:
        raise ValidationError("porta worker só 8795-8799")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise ValidationError("host tem de ser um IPv4 (ex. 192.168.1.20)")
    if not (ip.is_private or ip.is_loopback):
        raise ValidationError("só IPs privados ou loopback — sem Internet pública")
    label = str(args.get("label") or host)[:40]
    return {"host": host, "port": port, "label": label}


def register_gpu_worker(args, ctx) -> dict:
    a = _v_reg(args)
    if ctx.dry():
        return {"dry_run": True, **a, "nota": "não registo o worker sem AUTORIZO"}
    public = manager.register_worker(a["host"], a["port"], a["label"])
    st = manager.worker_status(a["host"], a["port"])
    return {"registered": public, "status": st}


register(ToolSpec("register_gpu_worker", register_gpu_worker, _v_reg, risk="medium", mutating=True,
                  summary="Regista um worker na LAN privada (Aura liga outbound; 8791 continua localhost)"))


def _v_job(args) -> dict:
    a = _v_reg(args)
    prompt = str((args or {}).get("prompt") or (args or {}).get("text") or "").strip()
    if not prompt or len(prompt) > 4000:
        raise ValidationError("prompt vazio ou >4000")
    a["prompt"] = prompt
    return a


def send_gpu_job(args, ctx) -> dict:
    a = _v_job(args)
    if ctx.dry():
        return {"dry_run": True, "host": a["host"], "nota": "não envio trabalho sem AUTORIZO"}
    payload = {"kind": "ollama_chat",
               "messages": [{"role": "user", "content": a["prompt"]}],
               "num_ctx": 1024, "num_predict": 256}
    return manager.send_job(a["host"], a["port"], payload)


register(ToolSpec("send_gpu_job", send_gpu_job, _v_job, risk="medium", mutating=True,
                  summary="Envia um pedido de inferência ao worker remoto e recebe o resultado"))


def gpu_share_status(args, ctx) -> dict:
    out = []
    for w in manager.list_workers():
        st = manager.worker_status(w["host"], w["port"], w.get("token") or "")
        out.append({"host": w["host"], "port": w["port"], "status": st})
    if not out:
        return {"workers": [], "nota": "nenhum worker. Alfred, exporta worker gpu  → copia o ZIP."}
    return {"workers": out}


register(ToolSpec("gpu_share_status", gpu_share_status, _v0, risk="low", mutating=False,
                  summary="Pinge os workers e mostra pausa/VRAM/jogos"))
