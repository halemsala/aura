# bridge/jarvis/skills/plugins/windows_master.py
"""
Skill: Windows Master
Controla o sistema operacional: abrir apps, organizar janelas.
"""
import subprocess
import logging
from typing import Dict

logger = logging.getLogger("aura.skill.windows")

try:
    import pygetwindow as gw
    GW_AVAILABLE = True
except ImportError:
    GW_AVAILABLE = False
    gw = None


class Skill:
    def __init__(self):
        self.description = "Controla o Windows. Acoes: open_app, focus_window, minimize_all, tile_windows."

    def run(self, action: str, args: Dict) -> str:
        try:
            if action == "open_app":
                app_name = str(args.get("app_name", "") or "")
                if not app_name or any(c in app_name for c in "&|<>^%"):
                    return "app_name invalido."
                subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=False)
                return f"Abrindo o aplicativo {app_name}."

            elif action == "focus_window":
                if not GW_AVAILABLE:
                    return "pygetwindow nao instalado."
                title_query = args.get("title", "")
                windows = gw.getWindowsWithTitle(title_query)
                if windows:
                    win = windows[0]
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                    return f"Janela focada: {win.title}."
                return f"Nenhuma janela encontrada com o titulo: {title_query}."

            elif action == "minimize_all":
                if not GW_AVAILABLE:
                    return "pygetwindow nao instalado."
                for win in gw.getAllWindows():
                    if win.title and not win.isMinimized:
                        win.minimize()
                return "Todas as janelas foram minimizadas."

            elif action == "tile_windows":
                if not GW_AVAILABLE:
                    return "pygetwindow nao instalado."
                windows = [w for w in gw.getAllWindows() if w.title and not w.isMinimized]
                if len(windows) >= 2:
                    screen_w, screen_h = gw.size()
                    windows[0].moveTo(0, 0)
                    windows[0].resizeTo(screen_w // 2, screen_h)
                    windows[1].moveTo(screen_w // 2, 0)
                    windows[1].resizeTo(screen_w // 2, screen_h)
                    return "Janelas organizadas lado a lado."
            return "Acao do Windows nao reconhecida."
        except Exception as e:
            logger.error("Erro no Windows Master: %s", e)
            return f"Falha ao executar acao no Windows: {e}"
