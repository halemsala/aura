"""Abrir programas Windows a partir de allowlist. Sem shell com texto do modelo."""
import os
import subprocess
from pathlib import Path

from ..registry import ToolSpec, register
from ..validators import ValidationError, normalize

APP_CANDIDATES = {
    "photoshop": [
        r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
        r"C:\Program Files\Adobe\Adobe Photoshop 2022\Photoshop.exe",
    ],
    "illustrator": [
        r"C:\Program Files\Adobe\Adobe Illustrator 2025\Support Files\Contents\Windows\Illustrator.exe",
        r"C:\Program Files\Adobe\Adobe Illustrator 2024\Support Files\Contents\Windows\Illustrator.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
    "notepad": [r"C:\Windows\System32\notepad.exe"],
    "paint": [r"C:\Windows\System32\mspaint.exe"],
    "explorer": [r"C:\Windows\explorer.exe"],
    "code": [
        str(Path.home() / r"AppData\Local\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ],
    "word": [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ],
    "excel": [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
}

ALIASES = {
    "ps": "photoshop", "adobe photoshop": "photoshop", "photo shop": "photoshop",
    "ai": "illustrator", "navegador": "chrome", "google": "chrome",
    "bloco de notas": "notepad", "explorador": "explorer", "ficheiros": "explorer",
    "vscode": "code", "vs code": "code", "word": "word", "excel": "excel",
}


URI_APPS = {
    "camera": "microsoft.windows.camera:",
    "camara": "microsoft.windows.camera:",
}

ALIASES.update({
    "câmara": "camera", "camera": "camera", "webcam": "camera", "web cam": "camera",
})


def _resolve_app(name: str):
    key = ALIASES.get(normalize(name), normalize(name).replace(" ", ""))
    if key in URI_APPS:
        return URI_APPS[key]
    if key not in APP_CANDIDATES:
        raise ValidationError(f"app '{name}' fora da allowlist: {sorted(list(APP_CANDIDATES)+list(URI_APPS))}")
    for cand in APP_CANDIDATES[key]:
        p = Path(cand)
        if p.is_file():
            return p
    raise ValidationError(f"{key} não está instalado nos caminhos conhecidos")


def _v_open(args) -> dict:
    name = str((args or {}).get("app") or (args or {}).get("name") or "").strip()
    if not name:
        raise ValidationError("indica a app (photoshop, chrome, notepad, explorer, code, word, excel)")
    exe = _resolve_app(name)
    return {"app": name, "exe": str(exe)}


def open_app(args, ctx) -> dict:
    a = _v_open(args)
    if ctx.dry():
        return {"dry_run": True, "app": a["app"], "exe": a["exe"],
                "nota": "app NÃO aberta. AUTORIZO para lançar (usa GPU/RAM)."}
    target = a["exe"]
    if isinstance(target, str) and (target.startswith("microsoft.") or target.endswith(":")):
        os.startfile(target)  # URI da Câmara do Windows — pedido explícito
        return {"opened": True, "app": a["app"], "exe": target, "kind": "uri"}
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(target)], cwd=str(Path(target).parent), creationflags=flags)
    return {"opened": True, "app": a["app"], "exe": str(target)}


def list_apps(args, ctx) -> dict:
    found = [{"app": "camera", "installed": os.name == "nt", "exe": URI_APPS["camera"]}]
    for name, cands in APP_CANDIDATES.items():
        exe = next((c for c in cands if Path(c).is_file()), None)
        found.append({"app": name, "installed": bool(exe), "exe": exe})
    return {"apps": found}


register(ToolSpec("open_app", open_app, _v_open, risk="medium", mutating=True,
                  summary="Abre app allowlisted (Photoshop, Chrome, Explorer, …). AUTORIZO. Sem shell livre."))
register(ToolSpec("list_apps", list_apps, lambda a: {}, risk="low", mutating=False,
                  summary="Lista programas Windows conhecidos e se estão instalados"))
