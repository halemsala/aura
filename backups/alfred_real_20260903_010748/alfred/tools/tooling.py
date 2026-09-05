"""Rever / instalar / desinstalar / recarregar ferramentas-plugin."""
import json
import time
from pathlib import Path

from .. import paths, plugin_loader, registry, tool_review
from ..locks import FileLock
from ..registry import ToolSpec, register
from ..validators import ValidationError

CORE_PROTECTED = set()


def _v_list(args) -> dict:
    return {}


def list_tools(args, ctx) -> dict:
    return {"tools": registry.capabilities(), "core": sorted(registry.CORE_NAMES),
            "plugins_dir": str(paths.PLUGINS_DIR)}


register(ToolSpec("list_tools", list_tools, _v_list, risk="low", mutating=False,
                  summary="Lista ferramentas core e plugins do Alfred"))


def _v_review(args) -> dict:
    args = args or {}
    source = str(args.get("source") or "")
    path = str(args.get("path") or "").strip()
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = paths.PROJECT_ROOT / p
        p = p.resolve()
        allowed = (paths.STAGING_DIR, paths.PLUGINS_DIR, paths.PROJECT_ROOT / "alfred")
        if not any(str(p).casefold().startswith(str(a.resolve()).casefold()) for a in allowed):
            raise ValidationError("path de revisão fora da allowlist")
        if p.suffix.lower() != ".py" or not p.is_file():
            raise ValidationError("só ficheiros .py existentes")
        source = p.read_text(encoding="utf-8")
        return {"source": source, "path": str(p), "name": str(args.get("name") or p.stem)}
    if not source.strip():
        raise ValidationError("envia 'source' (código) ou 'path' dentro de C:\\aura\\alfred")
    return {"source": source, "path": "", "name": str(args.get("name") or "")}


def review_tool(args, ctx) -> dict:
    a = _v_review(args)
    report = tool_review.review_source(a["source"], suggested_name=a["name"])
    report_path = tool_review.write_review(report)
    report["report_file"] = str(report_path)
    report["phase"] = "pre-install"
    return report


register(ToolSpec("review_tool", review_tool, _v_review, risk="low", mutating=False,
                  summary="Revisão estática de código de ferramenta (não executa, não instala)"))


def _v_install(args) -> dict:
    a = _v_review(args)
    report = tool_review.review_source(a["source"], suggested_name=a["name"])
    if not report["ok"]:
        raise ValidationError("revisão recusou o código: " + "; ".join(report["blockers"]))
    name = report["manifest"]["name"]
    if not name:
        raise ValidationError("TOOL_NAME em falta")
    if registry.is_core(name):
        raise ValidationError(f"{name} é ferramenta de núcleo — recusado")
    return {"source": a["source"], "name": name, "review": report}


def install_tool(args, ctx) -> dict:
    a = _v_install(args)
    name = a["name"]
    dest = plugin_loader.plugin_path(name)
    if ctx.dry():
        return {"dry_run": True, "name": name, "dest": str(dest),
                "review": a["review"], "nota": "não instalo sem AUTORIZO"}
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = None
    dest.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(dest, timeout=8):
        if dest.exists():
            backup = paths.BACKUPS_DIR / "plugins" / f"{name}-{ts}.py"
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
        dest.write_text(a["source"], encoding="utf-8")
    post = {"phase": "post-install"}
    try:
        loaded = plugin_loader.register_plugin_module(name, dest, replace=True)
        post["compile"] = True
        post["loaded"] = loaded.get("loaded")
        post["review"] = loaded.get("review")
        if post["review"] and not post["review"].get("ok"):
            raise RuntimeError("pós-revisão recusou o módulo")
        # smoke: validate({}) must not crash the process; errors are ok
        try:
            registry.spec(name).validate({})
            post["validate_smoke"] = "ok"
        except Exception as e:  # noqa: BLE001
            post["validate_smoke"] = f"{type(e).__name__}: {e}"[:200]
    except Exception as e:  # noqa: BLE001
        post["error"] = f"{type(e).__name__}: {e}"
        if backup and backup.exists():
            dest.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
            try:
                plugin_loader.register_plugin_module(name, dest, replace=True)
                post["rolled_back"] = True
            except Exception as e2:  # noqa: BLE001
                post["rollback_error"] = str(e2)[:200]
        else:
            try:
                if dest.exists():
                    dest.unlink()
                plugin_loader.unload_plugin(name)
                post["removed_failed_install"] = True
            except Exception:
                pass
        return {"installed": False, "name": name, "backup": str(backup or ""),
                "pre_review": a["review"], "post_review": post, "status": "failed"}
    tool_review.write_review({"ok": True, "manifest": a["review"]["manifest"],
                              "pre": a["review"], "post": post, "installed": True})
    return {"installed": True, "name": name, "path": str(dest), "backup": str(backup or ""),
            "pre_review": a["review"], "post_review": post, "status": "completed"}


register(ToolSpec("install_tool", install_tool, _v_install, risk="high", mutating=True,
                  sensitive=False,
                  summary="Instala plugin após revisão (AUTORIZO). Rollback se a pós-revisão falhar."))


def _v_uninstall(args) -> dict:
    name = str((args or {}).get("name") or "").strip()
    if not tool_review.NAME_RE.match(name):
        raise ValidationError("nome de ferramenta inválido")
    if registry.is_core(name):
        raise ValidationError("não desinstalo ferramentas de núcleo")
    return {"name": name}


def uninstall_tool(args, ctx) -> dict:
    a = _v_uninstall(args)
    dest = plugin_loader.plugin_path(a["name"])
    if ctx.dry():
        return {"dry_run": True, "name": a["name"], "path": str(dest)}
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = None
    if dest.exists():
        backup = paths.BACKUPS_DIR / "plugins" / f"{a['name']}-uninstall-{ts}.py"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
        dest.unlink()
    try:
        plugin_loader.unload_plugin(a["name"])
    except Exception as e:  # noqa: BLE001
        return {"uninstalled": False, "error": str(e)[:200]}
    return {"uninstalled": True, "name": a["name"], "backup": str(backup or "")}


register(ToolSpec("uninstall_tool", uninstall_tool, _v_uninstall, risk="high",
                  mutating=True, sensitive=False,
                  summary="Remove um plugin (não remove ferramentas de núcleo)"))


def reload_plugins(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "não recarrego plugins em dry-run"}
    return plugin_loader.load_all_plugins()


register(ToolSpec("reload_plugins", reload_plugins, _v_list, risk="medium",
                  mutating=True, sensitive=False,
                  summary="Recarrega plugins da pasta alfred/tools/plugins"))
