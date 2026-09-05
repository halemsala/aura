"""Patches com backup datado, lock por ficheiro e rollback. Só dentro de C:\\aura."""
import difflib
import json
import time
from pathlib import Path

from .. import paths
from ..locks import FileBusy, FileLock
from ..registry import ToolSpec, register
from ..validators import ValidationError

PROJECT_ROOT = paths.PROJECT_ROOT
PATCH_LOG = paths.DATA_ROOT / "patches.jsonl"
ALLOWED_SUFFIX = {".py", ".json", ".txt", ".bat", ".cmd", ".md", ".toml", ".yml", ".yaml"}
ALLOWED_DIRS = (
    PROJECT_ROOT / "alfred",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "hermes_v10" / "scripts",
    PROJECT_ROOT / "hermes_v10" / "core",
    PROJECT_ROOT / "scripts",
)
BLOCKED_NAMES = {".env", "AURA_RUNTIME.env", "local_token"}


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_patch_path(raw: str) -> Path:
    raw = str(raw or "").strip()
    if not raw:
        raise ValidationError("caminho vazio")
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p = Path(p).resolve()
    if not _under(p, PROJECT_ROOT):
        raise ValidationError("patch só é permitido dentro de C:\\aura")
    if p.name in BLOCKED_NAMES or p.suffix.lower() == ".env":
        raise ValidationError("ficheiros de ambiente/segredos não podem ser patchados")
    if p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValidationError(f"extensão não permitida: {p.suffix}")
    if not any(_under(p, d) or p.parent == PROJECT_ROOT and p.suffix.lower() in {".bat", ".cmd", ".txt", ".md"}
               for d in ALLOWED_DIRS):
        if p.parent.resolve() != PROJECT_ROOT.resolve() or p.suffix.lower() not in {".bat", ".cmd", ".txt", ".md"}:
            raise ValidationError("caminho fora das pastas de patch allowlisted")
    return p


def _log(entry: dict) -> None:
    PATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PATCH_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _v_apply(args) -> dict:
    args = args or {}
    p = _resolve_patch_path(args.get("path") or "")
    content = args.get("content")
    if content is None:
        raise ValidationError("content obrigatório")
    text = str(content)
    if len(text) > 400_000:
        raise ValidationError("patch demasiado grande")
    return {"path": p, "content": text, "reason": str(args.get("reason") or "")[:200]}


def apply_patch(args, ctx) -> dict:
    a = _v_apply(args)
    p = a["path"]
    if ctx.dry():
        return {"dry_run": True, "path": str(p), "nota": "patch NÃO aplicado (dry-run)"}
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = None
    try:
        with FileLock(p, timeout=8):
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            backup_dir = paths.BACKUPS_DIR / "patches" / ts
            backup_dir.mkdir(parents=True, exist_ok=True)
            rel = p.relative_to(PROJECT_ROOT)
            backup = backup_dir / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                backup.write_text(old, encoding="utf-8")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(a["content"], encoding="utf-8")
            diff = "".join(difflib.unified_diff(
                old.splitlines(True), a["content"].splitlines(True),
                fromfile=str(rel), tofile=str(rel), n=3))[:20_000]
            entry = {"ts": ts, "path": str(p), "backup": str(backup) if p.exists() or backup.exists() else "",
                     "reason": a["reason"], "job_id": ctx.job_id, "diff": diff}
            _log(entry)
            return {"applied": True, "path": str(p), "backup": str(backup), "diff": diff,
                    "bytes": len(a["content"].encode("utf-8"))}
    except FileBusy as e:
        raise ValidationError(str(e)) from e


def _v_rollback(args) -> dict:
    return {"path": str((args or {}).get("path") or "").strip()}


def _last_patch(path_filter: str = "") -> dict:
    if not PATCH_LOG.exists():
        return {}
    last = {}
    for line in PATCH_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if path_filter and str(e.get("path", "")).replace("\\", "/").endswith(path_filter.replace("\\", "/")):
            last = e
        elif not path_filter:
            last = e
    return last


def rollback_last(args, ctx) -> dict:
    a = _v_rollback(args)
    last = _last_patch(a["path"])
    if not last:
        from ..checkpoint_cli import restore_last
        if ctx.dry():
            return {"dry_run": True, "nota": "restauraria o último checkpoint (sem patch registado)"}
        return restore_last()
    backup = Path(last.get("backup") or "")
    target = Path(last.get("path") or "")
    if ctx.dry():
        return {"dry_run": True, "path": str(target), "backup": str(backup)}
    if not backup.exists():
        raise ValidationError(f"backup do patch não existe: {backup}")
    if not target:
        raise ValidationError("registo de patch sem caminho")
    with FileLock(target, timeout=8):
        target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    _log({"ts": time.strftime("%Y%m%d-%H%M%S"), "path": str(target), "rollback_from": str(backup),
          "job_id": ctx.job_id})
    return {"rolled_back": True, "path": str(target), "from": str(backup)}


register(ToolSpec("apply_patch", apply_patch, _v_apply, risk="high", mutating=True, sensitive=True,
                  summary="Aplica um patch mínimo com backup datado (só C:\\aura, lock por ficheiro)"))
register(ToolSpec("rollback_last", rollback_last, _v_rollback, risk="high", mutating=True, sensitive=True,
                  summary="Restaura o último patch (ou o último checkpoint se não houver patch)"))
