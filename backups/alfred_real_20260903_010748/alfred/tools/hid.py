"""Teclado e rato. Nunca toca em pastas do Windows. Apagar continua noutro sítio, com AUTORIZO."""
from __future__ import annotations

import string

from ..registry import ToolSpec, register
from ..validators import ValidationError

ALLOWED_KEYS = {
    "enter", "tab", "esc", "escape", "space", "backspace", "delete",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
    "ctrl", "alt", "shift",
    *string.ascii_lowercase,
    *string.digits,
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
}

BLOCKED_COMBOS = {
    ("ctrl", "alt", "delete"),
    ("ctrl", "alt", "del"),
    ("win", "r"),
    ("win", "x"),
    ("alt", "f4"),
}


def _pg():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        return pyautogui
    except ImportError:
        return None


def _v0(args) -> dict:
    return {}


def _v_click(args) -> dict:
    args = args or {}
    x = args.get("x")
    y = args.get("y")
    button = str(args.get("button") or "left").lower()
    if button not in ("left", "right", "middle"):
        raise ValidationError("button left|right|middle")
    clicks = max(1, min(int(args.get("clicks") or 1), 3))
    out = {"button": button, "clicks": clicks}
    if x is not None and y is not None:
        out["x"] = int(x)
        out["y"] = int(y)
    return out


def mouse_click(args, ctx) -> dict:
    a = _v_click(args)
    pg = _pg()
    if pg is None:
        return {"ok": False, "error": "pyautogui não instalado — pip install pyautogui"}
    if ctx.dry():
        return {"dry_run": True, **a, "nota": "rato NÃO mexido. AUTORIZO para clicar."}
    if "x" in a:
        pg.click(a["x"], a["y"], clicks=a["clicks"], button=a["button"])
    else:
        pg.click(clicks=a["clicks"], button=a["button"])
    return {"ok": True, **a}


register(ToolSpec("mouse_click", mouse_click, _v_click, risk="medium", mutating=True,
                  summary="Clica com o rato (posição actual ou x,y). AUTORIZO. Failsafe: canto do ecrã."))


def _v_move(args) -> dict:
    args = args or {}
    try:
        x, y = int(args.get("x")), int(args.get("y"))
    except (TypeError, ValueError):
        raise ValidationError("x e y obrigatórios")
    return {"x": x, "y": y}


def mouse_move(args, ctx) -> dict:
    a = _v_move(args)
    pg = _pg()
    if pg is None:
        return {"ok": False, "error": "pyautogui não instalado"}
    if ctx.dry():
        return {"dry_run": True, **a}
    pg.moveTo(a["x"], a["y"], duration=0.15)
    return {"ok": True, **a}


register(ToolSpec("mouse_move", mouse_move, _v_move, risk="low", mutating=True,
                  summary="Move o rato para x,y. AUTORIZO."))


def _v_keys(args) -> dict:
    raw = str((args or {}).get("keys") or (args or {}).get("key") or "").strip().lower()
    if not raw:
        raise ValidationError("keys vazio")
    parts = [p.strip() for p in raw.replace("+", " ").replace(",", " ").split() if p.strip()]
    if not parts or len(parts) > 4:
        raise ValidationError("1 a 4 teclas")
    for p in parts:
        if p not in ALLOWED_KEYS:
            raise ValidationError(f"tecla não permitida: {p}")
    if tuple(parts) in BLOCKED_COMBOS:
        raise ValidationError("atalho de sistema bloqueado")
    return {"keys": parts}


def key_press(args, ctx) -> dict:
    a = _v_keys(args)
    pg = _pg()
    if pg is None:
        return {"ok": False, "error": "pyautogui não instalado"}
    if ctx.dry():
        return {"dry_run": True, **a, "nota": "teclado NÃO usado. AUTORIZO para pressionar."}
    if len(a["keys"]) == 1:
        pg.press(a["keys"][0])
    else:
        pg.hotkey(*a["keys"])
    return {"ok": True, **a}


register(ToolSpec("key_press", key_press, _v_keys, risk="medium", mutating=True,
                  summary="Pressiona teclas allowlisted (enter, tab, ctrl+c…). Sem Win+R nem pastas do Windows."))
