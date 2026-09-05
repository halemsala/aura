"""Carrega plugins de alfred/tools/plugins depois da revisão. Sem restart."""
import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from . import paths, registry, tool_review
from .registry import ToolSpec

log = logging.getLogger("alfred.plugins")


def plugin_path(name: str) -> Path:
    return paths.PLUGINS_DIR / f"{name}.py"


def _load_module(name: str, path: Path):
    mod_name = f"alfred.tools.plugins.{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"não consegui carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _wrap_validate(fn):
    def validate(args):
        if fn.__code__.co_argcount == 1:
            return fn(args)
        return fn(args, None)
    return validate


def _wrap_run(fn):
    def run(args, ctx):
        if fn.__code__.co_argcount == 1:
            return fn(args)
        return fn(args, ctx)
    return run


def register_plugin_module(name: str, path: Path, replace: bool = False) -> dict:
    src = path.read_text(encoding="utf-8")
    review = tool_review.review_source(src, suggested_name=name)
    if not review["ok"]:
        raise RuntimeError("plugin recusado na revisão: " + "; ".join(review["blockers"]))
    man = review["manifest"]
    if not man.get("name"):
        raise RuntimeError("plugin sem TOOL_NAME")
    if man["name"] != name:
        raise RuntimeError(f"TOOL_NAME={man['name']} ≠ ficheiro {name}.py")
    if registry.is_core(name):
        raise RuntimeError(f"{name} é ferramenta de núcleo")
    mod = _load_module(name, path)
    validate = getattr(mod, "validate", None)
    run = getattr(mod, "run", None)
    if not callable(validate) or not callable(run):
        raise RuntimeError("validate/run não são chamáveis")
    spec = ToolSpec(
        name=name,
        fn=_wrap_run(run),
        validate=_wrap_validate(validate),
        risk=man.get("risk") or "medium",
        mutating=bool(man.get("mutating", True)),
        sensitive=True,
        summary=str(man.get("summary") or name),
        origin="plugin",
    )
    registry.register(spec, replace=replace or name in registry.TOOLS)
    return {"loaded": True, "name": name, "review": review}


def load_all_plugins() -> dict:
    loaded, skipped = [], []
    paths.PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(paths.PLUGINS_DIR.glob("*.py")):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        name = p.stem
        try:
            register_plugin_module(name, p, replace=True)
            loaded.append(name)
        except Exception as e:  # noqa: BLE001
            log.warning("plugin skip %s: %s", name, e)
            skipped.append({"name": name, "error": str(e)[:200]})
    return {"loaded": loaded, "skipped": skipped}


def unload_plugin(name: str) -> dict:
    registry.unregister(name)
    mod_name = f"alfred.tools.plugins.{name}"
    sys.modules.pop(mod_name, None)
    return {"unloaded": name}
