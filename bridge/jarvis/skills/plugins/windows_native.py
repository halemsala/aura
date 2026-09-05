# bridge/jarvis/skills/plugins/windows_native.py
"""Automacao nativa Windows via pywinauto. Depende de SKILLS_ENABLED no skill_manager."""
import logging

logger = logging.getLogger("aura.skill.windows_native")


class Skill:
    def __init__(self):
        self.description = "Automacao nativa do Windows. Acoes: click_button_by_name."

    def run(self, action: str, args: dict) -> str:
        if action == "click_button_by_name":
            app_name = args.get("app", "photoshop.exe")
            button_name = args.get("button", "Salvar")
            try:
                from pywinauto.application import Application
                app = Application(backend="uia").connect(path=app_name)
                btn = app.window().child_window(title=button_name, control_type="Button")
                btn.click()
                return f"Botao '{button_name}' clicado com sucesso no {app_name}."
            except Exception as e:
                return f"Falha ao clicar no botao nativo: {e}"
        return "Acao nao reconhecida."
