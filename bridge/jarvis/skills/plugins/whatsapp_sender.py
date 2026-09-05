# bridge/jarvis/skills/plugins/whatsapp_sender.py
"""
Skill: WhatsApp Sender
Envia arquivos e mensagens via WhatsApp Desktop.

AVISO: Automacao de UI. Fragil e potencialmente abusiva.
WHATSAPP_SENDER_ENABLED controla a execucao real.
"""
import logging
import os
import subprocess
import time
from typing import Dict

logger = logging.getLogger("aura.skill.whatsapp")

WHATSAPP_SENDER_ENABLED = False  # OPT-IN sob supervisao


class Skill:
    def __init__(self):
        self.description = "Envia arquivos e mensagens pelo WhatsApp. Acoes: send_file."

    def _copy_file_to_clipboard(self, filepath: str):
        try:
            import win32clipboard as clip
        except ImportError:
            raise RuntimeError("pywin32 nao instalado.")
        filepath = os.path.abspath(filepath)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Arquivo nao encontrado: {filepath}")
        drop_format = clip.RegisterClipboardFormat("FileNameW")
        data = filepath.encode("utf-16-le") + b"\x00\x00"
        clip.OpenClipboard()
        clip.EmptyClipboard()
        clip.SetClipboardData(drop_format, data)
        clip.SetClipboardData(clip.CF_UNICODETEXT, filepath)
        clip.CloseClipboard()

    def run(self, action: str, args: Dict) -> str:
        if not WHATSAPP_SENDER_ENABLED:
            return "WHATSAPP_SENDER_ENABLED=False. Envio bloqueado (modo supervisao)."
        if action == "send_file":
            phone = args.get("phone", "").replace("+", "").replace(" ", "")
            filepath = args.get("file_path", "")
            caption = args.get("caption", "")
            try:
                import pyautogui
                self._copy_file_to_clipboard(filepath)
                wa_uri = f"whatsapp://send?phone={phone}&text={caption}"
                subprocess.Popen(["cmd", "/c", "start", "", wa_uri], shell=True)
                time.sleep(4)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(2)
                pyautogui.press("enter")
                time.sleep(1)
                return f"Arquivo enviado para {phone} via WhatsApp."
            except Exception as e:
                logger.error("Erro no WhatsApp Sender: %s", e)
                return f"Falha ao enviar arquivo: {e}"
        return "Acao do WhatsApp nao reconhecida."
