"""Automações estilo assistente: agenda, YouTube, pastas em lote, visão, boot Aura."""
from __future__ import annotations

import json
import re
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

from .. import paths
from ..registry import ToolSpec, register
from ..validators import ValidationError, home_dir, resolve_allowed
from . import capture, files

AGENDA = paths.DATA_ROOT / "agenda.json"


def _v0(args) -> dict:
    return {}


def _load_agenda() -> list:
    if not AGENDA.exists():
        return []
    try:
        return json.loads(AGENDA.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_agenda(items: list) -> None:
    AGENDA.parent.mkdir(parents=True, exist_ok=True)
    AGENDA.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _v_cal(args) -> dict:
    args = args or {}
    title = str(args.get("title") or args.get("text") or "").strip()[:200]
    when = str(args.get("when") or args.get("hora") or "").strip()[:80]
    if not title:
        raise ValidationError("título da agenda vazio")
    return {"title": title, "when": when or "hoje"}


def calendar_add(args, ctx) -> dict:
    a = _v_cal(args)
    if ctx.dry():
        return {"dry_run": True, **a, "nota": "não gravado. AUTORIZO para agendar."}
    items = _load_agenda()
    item = {"id": hex(int(time.time() * 1000))[2:], "title": a["title"], "when": a["when"],
            "ts": time.time()}
    items.append(item)
    _save_agenda(items[-200:])
    return {"saved": True, **item}


register(ToolSpec("calendar_add", calendar_add, _v_cal, risk="low", mutating=True,
                  summary="Agenda um compromisso local (linguagem natural)"))


def calendar_today(args, ctx) -> dict:
    items = _load_agenda()
    return {"count": len(items), "items": items[-20:], "path": str(AGENDA)}


register(ToolSpec("calendar_today", calendar_today, _v0, risk="low", mutating=False,
                  summary="Lista compromissos da agenda local"))


def _v_yt(args) -> dict:
    q = str((args or {}).get("query") or (args or {}).get("text") or "").strip()[:120]
    if not q:
        q = "música"
    return {"query": q}


def play_youtube(args, ctx) -> dict:
    a = _v_yt(args)
    url = "https://www.youtube.com/results?search_query=" + quote_plus(a["query"])
    if ctx.dry():
        return {"dry_run": True, "url": url, "nota": "YouTube NÃO aberto"}
    webbrowser.open(url, new=2)
    return {"opened": True, "url": url, "query": a["query"]}


register(ToolSpec("play_youtube", play_youtube, _v_yt, risk="low", mutating=True,
                  summary="Abre pesquisa no YouTube (música / vídeo)"))


def _v_batch(args) -> dict:
    args = args or {}
    names = args.get("names")
    if isinstance(names, str):
        names = [n.strip() for n in re.split(r"[,;]", names) if n.strip()]
    if not names:
        count = int(args.get("count") or 0)
        prefix = str(args.get("prefix") or "Pasta").strip() or "Pasta"
        start = int(args.get("start") or 1)
        if count < 1 or count > 20:
            raise ValidationError("count entre 1 e 20")
        names = [f"{prefix} {i}" for i in range(start, start + count)]
    names = [str(n).strip()[:60] for n in names if str(n).strip()]
    if not 1 <= len(names) <= 20:
        raise ValidationError("1 a 20 pastas")
    parent = resolve_allowed(args.get("parent") or "Desktop")
    return {"parent": str(parent), "names": names}


def create_folders_batch(args, ctx) -> dict:
    a = _v_batch(args)
    parent = Path(a["parent"])
    if ctx.dry():
        return {"dry_run": True, "parent": str(parent), "names": a["names"],
                "nota": "pastas NÃO criadas. AUTORIZO para criar."}
    created, existed = [], []
    parent.mkdir(parents=True, exist_ok=True)
    for name in a["names"]:
        p = parent / name
        if p.exists():
            existed.append(str(p))
        else:
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
    return {"created": created, "existed": existed, "parent": str(parent), "count": len(created)}


register(ToolSpec("create_folders_batch", create_folders_batch, _v_batch, risk="low", mutating=True,
                  summary="Cria várias pastas no Desktop (ex. Aula 1 a Aula 10)"))


def inspect_desktop(args, ctx) -> dict:
    listing = files.list_files({"path": "Desktop"}, ctx)
    moves, skipped = files._build_desktop_plan()
    by_cat = {}
    for m in moves:
        by_cat[m["category"]] = by_cat.get(m["category"], 0) + 1
    return {
        "path": listing.get("path"),
        "count": listing.get("count"),
        "sample": (listing.get("items") or [])[:40],
        "loose_files_to_organize": len(moves),
        "by_category": by_cat,
        "over_limit": skipped,
        "nota": "nada foi movido. Diz 'organiza o desktop' + AUTORIZO para agrupar.",
    }


register(ToolSpec("inspect_desktop", inspect_desktop, _v0, risk="low", mutating=False,
                  summary="Vê o Desktop: ficheiros soltos e categorias"))


def _color_name(bgr) -> str:
    b, g, r = [int(x) for x in bgr]
    if r > 180 and g < 90 and b < 90:
        return "vermelho"
    if r < 90 and g < 90 and b > 160:
        return "azul"
    if r < 90 and g > 160 and b < 90:
        return "verde"
    if r > 180 and g > 180 and b < 90:
        return "amarelo"
    if r > 200 and g > 200 and b > 200:
        return "claro / branco"
    if r < 50 and g < 50 and b < 50:
        return "escuro"
    if r > 140 and g > 90 and b < 80:
        return "laranja / castanho"
    if abs(r - g) < 30 and abs(g - b) < 30:
        return "cinza"
    return "misto"


def see_camera(args, ctx) -> dict:
    shot = capture.capture_camera(args or {}, ctx)
    if ctx.dry() or not shot.get("captured"):
        return shot
    desc = "Fotografia guardada."
    try:
        import cv2
        import numpy as np
        img = cv2.imread(shot["path"])
        if img is not None:
            h, w = img.shape[:2]
            small = cv2.resize(img, (48, 48))
            mean = small.mean(axis=(0, 1))
            color = _color_name(mean)
            faces = 0
            try:
                cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = len(cascade.detectMultiScale(gray, 1.2, 5))
            except Exception:
                faces = 0
            desc = (
                f"Estou a ver uma imagem {w} por {h} pixéis. "
                f"Tom dominante: {color}. "
                f"{'Há um rosto na frente da câmara.' if faces else 'Não detectei um rosto nítido.'} "
                "qwen3:8b é texto: não invento marca de copo nem modelo de guitarra. "
                f"Foto em {shot['path']}."
            )
    except Exception as e:
        desc = f"Foto em {shot.get('path')}. Análise extra falhou: {e}"
    shot["description"] = desc
    return shot


register(ToolSpec("see_camera", see_camera, capture._v_capture, risk="medium", mutating=True,
                  summary="Tira foto da câmara e descreve o que dá para ver (sem inventar marcas)"))


def see_screen(args, ctx) -> dict:
    desk = inspect_desktop({}, ctx)
    shot = capture.capture_screen(args or {}, ctx)
    return {"desktop": desk, "screenshot": shot}


register(ToolSpec("see_screen", see_screen, capture._v_capture, risk="medium", mutating=True,
                  summary="Captura o ecrã e descreve o Desktop (ficheiros, janela)"))


def boot_aura_stack(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "não arranco serviços. AUTORIZO para subir o Aura."}
    scripts = str(paths.PROJECT_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import aura_chat_agents as ag
    core = ag.restart_service("core")
    desk = None
    if bool((args or {}).get("desktop")):
        desk = ag.open_desktop()
    return {
        "ok": True,
        "core": str(core)[:900],
        "desktop": desk,
        "nota": "Ollama e Hermes não são mortos. Alfred já estava neste processo.",
    }


register(ToolSpec("boot_aura_stack", boot_aura_stack, _v0, risk="high", mutating=True,
                  summary="Sobe Bridge/Engine/Matriz/Voz se o Aura estiver fechado. Não mata Ollama."))
