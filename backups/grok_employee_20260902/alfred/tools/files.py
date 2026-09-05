import os, shutil, time
from pathlib import Path
from .. import paths
from ..executor import ToolError
from ..registry import ToolSpec, register
from ..validators import ValidationError, detect_secrets, home_dir, resolve_allowed

MAX_READ = 200_000
ORGANIZE_LIMIT = 100
MAX_WRITE = 50_000

CATEGORIES = {
    "Imagens": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".heic"},
    "Documentos": {".pdf", ".doc", ".docx", ".txt", ".md", ".odt", ".rtf"},
    "FolhasCalculo": {".xls", ".xlsx", ".csv", ".ods"},
    "Apresentacoes": {".ppt", ".pptx", ".odp"},
    "Arquivos": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Instaladores": {".exe", ".msi"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm"},
    "Codigo": {".py", ".js", ".html", ".css", ".json", ".bat", ".ps1", ".sh"},
}

def category_for(ext: str) -> str:
    ext = ext.casefold()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Outros"


# ---------- create_folder ----------
def _v_create_folder(args) -> dict:
    args = args or {}
    name = str(args.get("name") or "").strip()
    if not name or len(name) > 80:
        raise ValidationError("nome de pasta inválido (vazio ou >80 chars)")
    if any(sep in name for sep in ("\\", "/", "..", ":")):
        raise ValidationError("nome de pasta não pode conter caminhos")
    parent_raw = args.get("parent") or "Desktop"
    parent = resolve_allowed(parent_raw)
    return {"path": str(parent / name), "name": name}

def create_folder(args, ctx) -> dict:
    a = _v_create_folder(args)
    path = Path(a["path"])
    if ctx.dry():
        return {"dry_run": True, "path": str(path), "nota": "pasta NÃO criada (dry-run)"}
    if path.exists():
        return {"created": False, "existed": True, "path": str(path)}
    path.mkdir(parents=True)
    return {"created": True, "path": str(path)}

register(ToolSpec("create_folder", create_folder, _v_create_folder, risk="low", mutating=True,
                  summary="Cria uma pasta em Desktop/Documents/Downloads/data-alfred"))


# ---------- list_files ----------
def _v_list_files(args) -> dict:
    return {"path": resolve_allowed((args or {}).get("path") or "Desktop")}

def list_files(args, ctx) -> dict:
    p = _v_list_files(args)["path"]
    if not p.exists():
        raise ToolError(f"caminho não existe: {p}")
    items = []
    it = [p] if p.is_file() else sorted(p.iterdir())
    for f in it[:500]:
        try:
            items.append({"name": f.name, "dir": f.is_dir(), "size": f.stat().st_size})
        except OSError:
            continue
    return {"path": str(p), "count": len(items), "items": items}

register(ToolSpec("list_files", list_files, _v_list_files, risk="low", mutating=False,
                  summary="Lista ficheiros (só leitura) numa pasta allowlisted"))


# ---------- organize_desktop ----------
def _v_organize(args) -> dict:
    return {}

def _build_desktop_plan():
    desk = home_dir() / "Desktop"
    moves, skipped = [], 0
    for item in sorted(desk.iterdir()):
        if item.is_dir() or item.name.startswith(".") or item.suffix.casefold() == ".lnk":
            continue
        if len(moves) >= ORGANIZE_LIMIT:
            skipped += 1
            continue
        cat = category_for(item.suffix)
        dest_dir = desk / cat
        dest = dest_dir / item.name
        k = 1
        while dest.exists():
            dest = dest_dir / f"{item.stem} ({k}){item.suffix}"
            k += 1
        moves.append({"from": str(item), "to": str(dest), "category": cat})
    return moves, skipped

def organize_desktop(args, ctx) -> dict:
    _v_organize(args)
    moves, skipped = _build_desktop_plan()
    if ctx.dry():
        return {"executed": False, "planned_moves": len(moves), "over_limit_skipped": skipped,
                "moves_preview": moves[:50], "nota": "plano apenas — responde AUTORIZO para executar; nada é apagado"}
    moved_list, done, errors = [], 0, []
    for m in moves:
        if ctx.cancelled():
            break
        try:
            Path(m["to"]).parent.mkdir(exist_ok=True)
            if Path(m["to"]).exists():
                errors.append(f"destino ocupado: {m['to']}")
                continue
            shutil.move(m["from"], m["to"])
            moved_list.append(m)
            done += 1
        except OSError as e:
            errors.append(f"{m['from']}: {e}")
    return {"executed": True, "moved": done, "planned": len(moves), "moved_list": moved_list,
            "errors": errors[:20], "deleted": 0}

def _rollback_organize(args, result, ctx) -> bool:
    if not result.get("executed"):
        return False
    for m in result.get("moved_list", []):
        try:
            shutil.move(m["to"], m["from"])
        except OSError:
            return False
    return True

register(ToolSpec("organize_desktop", organize_desktop, _v_organize, risk="medium", mutating=True,
                  summary="Organiza Desktop por categorias (máx 100 itens; nunca apaga; plano antes de executar)",
                  rollback=_rollback_organize))


# ---------- read_text_file ----------
def _v_read(args) -> dict:
    p = resolve_allowed((args or {}).get("path"))
    if not p.is_file():
        raise ValidationError(f"ficheiro inexistente: {p}")
    if p.stat().st_size > MAX_READ:
        raise ValidationError("ficheiro excede 200 KB")
    return {"path": p}

def read_text_file(args, ctx) -> dict:
    p = _v_read(args)["path"]
    data = p.read_text(encoding="utf-8", errors="replace")
    hits = detect_secrets(data)
    return {"path": str(p), "size": len(data),
            "content": "(conteúdo oculto: possível segredo detetado)" if hits else data,
            "secrets_redacted": bool(hits)}

register(ToolSpec("read_text_file", read_text_file, _v_read, risk="low", mutating=False,
                  summary="Lê ficheiro de texto allowlisted (máx 200 KB, segredos ocultados)"))


# ---------- write_text_file ----------
def _v_write(args) -> dict:
    args = args or {}
    p = resolve_allowed(args.get("path"))
    text = str(args.get("text") or "")
    if len(text) > MAX_WRITE:
        raise ValidationError("texto excede 50 000 caracteres")
    hits = detect_secrets(text)
    if hits:
        raise ValidationError("texto contém possível segredo — escrita bloqueada")
    return {"path": p, "text": text}

def write_text_file(args, ctx) -> dict:
    a = _v_write(args)
    if ctx.dry():
        return {"dry_run": True, "path": str(a["path"]), "nota": "ficheiro NÃO escrito (dry-run)"}
    backup = None
    if a["path"].exists():
        backup = a["path"].with_name(a["path"].name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(a["path"], backup)
    tmp = a["path"].with_name(a["path"].name + ".tmp-alfred")
    tmp.write_text(a["text"], encoding="utf-8")
    os.replace(tmp, a["path"])
    return {"written": True, "path": str(a["path"]), "backup": str(backup) if backup else None}

def _rollback_write(args, result, ctx) -> bool:
    b = (result or {}).get("backup")
    if b and Path(b).exists():
        shutil.copy2(b, Path(result["path"]))
        return True
    return False

register(ToolSpec("write_text_file", write_text_file, _v_write, risk="high", mutating=True, sensitive=True,
                  summary="Escreve ficheiro allowlisted (backup prévio; exige AUTORIZO + execution_allowed/token)",
                  rollback=_rollback_write))
