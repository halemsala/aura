import time
from .. import paths
from ..config import get_config
from ..ollama_client import OllamaClient, OllamaUnavailable
from ..registry import ToolSpec, register


def _vision_note() -> str:
    cfg = get_config()
    vm = (cfg.get("vision_model") or "").strip()
    if vm:
        try:
            if vm in OllamaClient(cfg).installed_models():
                return f"modelo de visão '{vm}' verificado e disponível para interpretação."
            return f"ALFRED_VISION_MODEL='{vm}' configurado mas AUSENTE em /api/tags — não será usado."
        except OllamaUnavailable:
            return "Ollama offline — imagem guardada, sem interpretação."
    return ("qwen3:8b é um modelo de TEXTO: a imagem foi guardada mas NÃO pode ser interpretada "
            "sem um modelo multimodal (configura ALFRED_VISION_MODEL se existir um instalado).")

def _cleanup_old() -> int:
    hours = float(get_config().get("capture_retention_hours", 24))
    cutoff = time.time() - hours * 3600
    removed = 0
    for f in paths.CAPTURES_DIR.glob("*"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed

def _v_capture(args) -> dict:
    return {"cleanup": bool((args or {}).get("cleanup", True))}

def capture_screen(args, ctx) -> dict:
    _v_capture(args)
    if ctx.dry():
        return {"dry_run": True, "nota": "nada capturado (dry-run)"}
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"captured": False, "error": "Pillow não instalado — pip install Pillow"}
    img = ImageGrab.grab()
    path = paths.CAPTURES_DIR / f"screen-{time.strftime('%Y%m%d-%H%M%S')}.png"
    img.save(path)
    return {"captured": True, "path": str(path), "uploaded": False,
            "cleaned_old": _cleanup_old(), "note": _vision_note()}

register(ToolSpec("capture_screen", capture_screen, _v_capture, risk="medium", mutating=True,
                  summary="Captura de tela para ficheiro local (sem upload; sem interpretação sem modelo de visão)"))


def capture_camera(args, ctx) -> dict:
    _v_capture(args)
    if ctx.dry():
        return {"dry_run": True, "nota": "nada capturado (dry-run)"}
    try:
        import cv2
    except ImportError:
        return {"captured": False, "error": "OpenCV não instalado — pip install opencv-python"}
    cap = cv2.VideoCapture(0)
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        return {"captured": False, "error": "câmara indisponível ou permissão negada pelo sistema"}
    path = paths.CAPTURES_DIR / f"camera-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
    cv2.imwrite(str(path), frame)
    return {"captured": True, "path": str(path), "uploaded": False,
            "cleaned_old": _cleanup_old(), "note": _vision_note()}

register(ToolSpec("capture_camera", capture_camera, _v_capture, risk="medium", mutating=True,
                  summary="Captura fotografia da câmara para ficheiro local (sem upload)"))
