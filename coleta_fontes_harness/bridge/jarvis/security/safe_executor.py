# -*- coding: utf-8 -*-
"""Safe Executor — mouse/teclado em sandbox. CPU only. Anti-Bet Shield."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("aura.safe_executor")

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # canto do ecrã = abort
    pyautogui.PAUSE = 0.35
    HAS_PYAUTOGUI = True
except Exception:
    pyautogui = None
    HAS_PYAUTOGUI = False

try:
    import pygetwindow as gw
    HAS_GW = True
except Exception:
    gw = None
    HAS_GW = False

FORBIDDEN_PATHS = [
    os.environ.get("SystemRoot", r"C:\Windows"),
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
]

BLOCKED_WINDOW_KEYWORDS = [
    "bet365", "sokkerpro", "betfair", "aposta", "sportingbet",
    "betano", "pinnacle", "stake.com", "1xbet",
]


class SafeExecutor:
    def __init__(self) -> None:
        self.authorized_deletes: List[str] = []
        logger.info("SafeExecutor activo (pyautogui=%s, pygetwindow=%s)", HAS_PYAUTOGUI, HAS_GW)

    def _is_path_safe(self, filepath: str) -> bool:
        try:
            fp = str(Path(filepath).resolve())
        except Exception:
            return False
        low = fp.lower()
        for forbidden in FORBIDDEN_PATHS:
            if forbidden and low.startswith(str(forbidden).lower()):
                return False
        if any(x in low for x in (".env", "credential", "id_rsa", "private_key")):
            return False
        return True

    def _is_active_window_safe(self) -> bool:
        if not HAS_GW:
            return True
        try:
            active = gw.getActiveWindow()
            if not active:
                return True
            title = (active.title or "").lower()
            for kw in BLOCKED_WINDOW_KEYWORDS:
                if kw in title:
                    logger.error("Anti-Bet Shield: janela bloqueada -> %s", active.title)
                    return False
        except Exception:
            pass
        return True

    def move_mouse(self, x: int, y: int) -> bool:
        if not HAS_PYAUTOGUI:
            return False
        try:
            pyautogui.moveTo(int(x), int(y), duration=0.25)
            return True
        except Exception as e:
            logger.error("move_mouse: %s", e)
            return False

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> bool:
        if not HAS_PYAUTOGUI:
            return False
        if not self._is_active_window_safe():
            return False
        try:
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y), button=button)
            else:
                pyautogui.click(button=button)
            return True
        except Exception as e:
            logger.error("click: %s", e)
            return False

    def type_text(self, text: str) -> bool:
        if not HAS_PYAUTOGUI:
            return False
        if not self._is_active_window_safe():
            return False
        try:
            pyautogui.write(str(text)[:500], interval=0.03)
            return True
        except Exception as e:
            logger.error("type_text: %s", e)
            return False

    def press_key(self, key: str) -> bool:
        if not HAS_PYAUTOGUI:
            return False
        if not self._is_active_window_safe():
            return False
        try:
            pyautogui.press(str(key))
            return True
        except Exception as e:
            logger.error("press_key: %s", e)
            return False

    def authorize_delete(self, filepath: str) -> bool:
        if self._is_path_safe(filepath):
            self.authorized_deletes.append(filepath)
            return True
        return False

    def safe_delete(self, filepath: str) -> bool:
        if filepath not in self.authorized_deletes:
            logger.warning("delete sem AUTORIZO: %s", filepath)
            return False
        if not self._is_path_safe(filepath):
            return False
        try:
            p = Path(filepath)
            if p.is_file():
                p.unlink()
                self.authorized_deletes.remove(filepath)
                return True
        except Exception as e:
            logger.error("safe_delete: %s", e)
        return False


SAFE_EXECUTOR = SafeExecutor()
