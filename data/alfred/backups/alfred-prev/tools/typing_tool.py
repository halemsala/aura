from ..executor import ToolError
from ..registry import ToolSpec, register
from ..validators import ValidationError, detect_secrets

MAX_TYPE = 1500

def _validate(args) -> dict:
    args = args or {}
    text = str(args.get("text") or "")
    if not text.strip():
        raise ValidationError("texto vazio")
    if len(text) > MAX_TYPE:
        raise ValidationError(f"texto excede {MAX_TYPE} caracteres")
    hits = detect_secrets(text)
    if hits:
        raise ValidationError("texto contém possível segredo — bloqueado")
    mode = args.get("mode", "write")
    if mode not in ("write", "clipboard"):
        raise ValidationError("mode deve ser 'write' ou 'clipboard'")
    return {"text": text, "mode": mode}

def type_text(args, ctx) -> dict:
    a = _validate(args)
    if ctx.dry():
        return {"dry_run": True, "chars": len(a["text"]), "nota": "nada foi escrito (dry-run)"}
    try:
        import pyautogui  # noqa: F401
    except ImportError:
        return {"typed": False, "error": "pyautogui não instalado — instala com: pip install pyautogui pyperclip"}
    if a["mode"] == "clipboard":
        if not ctx.authorized:
            raise ToolError("modo clipboard (Ctrl+V) exige autorização explícita (AUTORIZO)")
        try:
            import pyperclip
        except ImportError:
            return {"typed": False, "error": "pyperclip não instalado — pip install pyperclip"}
        pyperclip.copy(a["text"])
        import pyautogui
        pyautogui.hotkey("ctrl", "v")
        return {"typed": True, "mode": "clipboard", "chars": len(a["text"])}
    import pyautogui
    try:
        pyautogui.write(a["text"], interval=0.01)
        return {"typed": True, "mode": "write", "chars": len(a["text"])}
    except Exception as e:  # noqa: BLE001
        return {"typed": False, "error": f"escrita directa falhou ({e}); usa mode='clipboard' com AUTORIZO"}

register(ToolSpec("type_text", type_text, _validate, risk="medium", mutating=True,
                  summary=f"Escreve texto na janela activa (máx {MAX_TYPE} chars; sem segredos; clipboard só com AUTORIZO)"))
