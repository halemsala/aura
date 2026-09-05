# bridge/jarvis/skills/plugins/whatsapp_operator.py
"""
Skill: WhatsApp Operator (modo humano — teclado/mouse, zero API)

O LLM só passa INTENÇÃO. Fluxos são macros fixas.
4 anéis anti-catástrofe:
  1) Janela correta em foco (e nunca em casa de apostas)
  2) Título da conversa verificado após busca
  3) Conteúdo via clipboard nativo (texto/arquivo)
  4) Two-man rule: nada é enviado sem _confirmado_pelo_operador=True

Ações: send_message, send_file
Dependências: pyautogui, pygetwindow, pyperclip, pywin32 (CF_HDROP)
"""
from __future__ import annotations

import logging
import os
import struct
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("aura.skill.whatsapp_operator")

# Ritmo humano: Electron perde cliques rápidos demais
try:
    import pyautogui
    pyautogui.PAUSE = 0.4
    pyautogui.FAILSAFE = True
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

def _env_enabled(var: str) -> bool:
    return os.environ.get(var, "0").strip().lower() in ("1", "true", "yes", "on")


WINDOW_KEYWORD = "whatsapp"
ENV_FLAG = "AURA_WHATSAPP_OPERATOR_ENABLED"
BLOCKED_WINDOW_KEYWORDS = [
    "bet365", "sokkerpro", "betfair", "aposta", "sportingbet",
    "betano", "pinnacle", "stake.com", "1xbet", "blaze",
]

# Tempos padrão (substituíveis pelo gravador de macro → macros_latencies.json)
DEFAULT_LATENCIES = {
    "after_focus": 1.0,
    "after_ctrl_f": 0.8,
    "after_type_contact": 1.5,
    "after_enter_contact": 1.2,
    "after_paste_text": 0.5,
    "after_paste_file": 2.0,
    "after_send": 0.6,
    "type_interval": 0.06,
}


def _load_latencies() -> Dict[str, float]:
    """Carrega latências gravadas pelo macro_recorder, se existirem."""
    candidates = [
        Path("bridge/jarvis/tools/macros_latencies.json"),
        Path("engine/data/macros_latencies.json"),
        Path(__file__).resolve().parent.parent.parent / "tools" / "macros_latencies.json",
    ]
    for p in candidates:
        try:
            if p.is_file():
                import json
                data = json.loads(p.read_text(encoding="utf-8"))
                wa = data.get("whatsapp") or data.get("default") or {}
                merged = dict(DEFAULT_LATENCIES)
                merged.update({k: float(v) for k, v in wa.items() if k in merged})
                return merged
        except Exception as e:
            logger.debug("latencies load fail %s: %s", p, e)
    return dict(DEFAULT_LATENCIES)


def _focus_app(keyword: str) -> Optional[Any]:
    if not HAS_GW:
        return None
    wins = [w for w in gw.getAllWindows() if keyword in (w.title or "").lower()]
    if not wins:
        return None
    w = wins[0]
    try:
        if getattr(w, "isMinimized", False):
            w.restore()
        w.activate()
        time.sleep(_load_latencies()["after_focus"])
        return w
    except Exception as e:
        logger.error("focus_app fail: %s", e)
        return None


def _is_window_safe(title: str) -> bool:
    low = (title or "").lower()
    return not any(kw in low for kw in BLOCKED_WINDOW_KEYWORDS)


def _clipboard_file(filepath: str) -> bool:
    """Coloca ARQUIVO no clipboard (CF_HDROP) — equivalente a Ctrl+C no Explorer."""
    try:
        import win32clipboard
    except ImportError:
        logger.error("pywin32 não instalado — clipboard de arquivo indisponível")
        return False

    p = str(Path(filepath).resolve())
    if not Path(p).is_file():
        return False

    # DROPFILES: pFiles=20, pt(0,0), fNC=0, fWide=1 + path UTF-16-LE + null duplo
    blob = struct.pack("IiiII", 20, 0, 0, 0, 1) + p.encode("utf-16-le") + b"\x00\x00"
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_HDROP, blob)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        logger.error("clipboard file fail: %s", e)
        return False


def _clipboard_text(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text or "")
        return True
    except Exception as e:
        logger.error("clipboard text fail: %s", e)
        return False


class Skill:
    def __init__(self):
        self.description = (
            "Envia mensagens/arquivos por WhatsApp Desktop como humano "
            "(teclado/mouse, sem API). Ações: send_message, send_file. "
            "Requer AURA_WHATSAPP_OPERATOR_ENABLED=1 e confirmação por voz."
        )
        self.window_keyword = WINDOW_KEYWORD
        self.env_flag = ENV_FLAG

    def run(self, action: str, args: Dict[str, Any]) -> str:
        if not _env_enabled(self.env_flag):
            return (
                f"{self.env_flag}=0. "
                f"Ative com set {self.env_flag}=1 sob supervisão."
            )
        if not HAS_PYAUTOGUI or not HAS_GW:
            return "Dependências em falta: pyautogui e/ou pygetwindow."

        contato = (args.get("contato") or args.get("contact") or "").strip()
        if not contato:
            return "Preciso do nome do contato."

        lat = _load_latencies()

        # ── ANEL 1: janela certa em foco (e NUNCA numa janela de aposta) ──
        win = _focus_app(self.window_keyword)
        if not win:
            return f"{self.window_keyword.title()} Desktop não está aberto."

        active_title = getattr(gw.getActiveWindow(), "title", "") if HAS_GW else ""
        if not _is_window_safe(active_title):
            return f"ABORTADO: escudo anti-aposta — janela suspeita: {active_title}"

        # ── Busca o contato (macro fixa: Ctrl+F → nome → Enter) ──
        pyautogui.hotkey("ctrl", "f")
        time.sleep(lat["after_ctrl_f"])
        pyautogui.write(contato, interval=lat["type_interval"])
        time.sleep(lat["after_type_contact"])
        pyautogui.press("enter")
        time.sleep(lat["after_enter_contact"])

        # ── ANEL 2: VERIFICA o título — se a conversa aberta não contém o alvo, ABORTA ──
        active = gw.getActiveWindow() if HAS_GW else None
        title = (getattr(active, "title", "") or "").lower()
        # Aceita o primeiro token do nome (ex.: "João Silva" → "joão")
        token = contato.lower().split()[0]
        if not active or token not in title:
            try:
                pyautogui.press("esc")
            except Exception:
                pass
            return (
                f"ABORTADO: conversa aberta não confere com '{contato}' "
                f"(título: {getattr(active, 'title', '?')}). Verifique o nome na agenda."
            )

        # ── ANEL 3: conteúdo entra no clipboard, não digitado direto ──
        if action == "send_message":
            texto = args.get("texto") or args.get("text") or ""
            if not texto:
                return "Texto da mensagem vazio."
            if not _clipboard_text(texto):
                return "Falha ao copiar texto para o clipboard."
            pyautogui.hotkey("ctrl", "v")
            time.sleep(lat["after_paste_text"])

        elif action == "send_file":
            path = args.get("path") or args.get("file_path") or args.get("filepath") or ""
            if not _clipboard_file(path):
                return f"Arquivo não encontrado ou clipboard falhou: {path}"
            pyautogui.hotkey("ctrl", "v")
            time.sleep(lat["after_paste_file"])
            # Caption opcional após o preview do anexo
            caption = args.get("caption") or args.get("texto") or ""
            if caption:
                if _clipboard_text(caption):
                    pyautogui.hotkey("ctrl", "v")
                    time.sleep(lat["after_paste_text"])

        else:
            return f"Ação desconhecida: {action}. Use send_message ou send_file."

        # ── ANEL 4: two-man rule — nada é enviado sem confirmação ──
        if not args.get("_confirmado_pelo_operador"):
            preview = ""
            if action == "send_message":
                preview = (args.get("texto") or args.get("text") or "")[:80]
            else:
                preview = Path(args.get("path") or args.get("file_path") or "?").name
            return (
                f"PRONTO PARA ENVIAR para {contato} via {self.window_keyword.title()} "
                f"(janela verificada: {getattr(active, 'title', '?')}). "
                f"Prévia: {preview!r}. "
                f"Confirme por voz dizendo 'confirmo' ou 'pode mandar' — nada foi enviado ainda."
            )

        pyautogui.press("enter")  # o único Enter que efetivamente envia
        time.sleep(lat["after_send"])
        return f"✅ Enviado para {contato} via {self.window_keyword.title()} (modo humano)."
