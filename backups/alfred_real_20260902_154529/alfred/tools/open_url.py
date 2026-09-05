import webbrowser
from ..executor import ToolError
from ..registry import ToolSpec, register
from ..validators import validate_url


def _validate(args) -> dict:
    return {"url": validate_url(str((args or {}).get("url", "")))}

def open_url(args: dict, ctx) -> dict:
    url = _validate(args)["url"]
    if ctx.dry():
        return {"dry_run": True, "url": url, "nota": "página NÃO foi aberta (dry-run)"}
    ok = webbrowser.open(url, new=2)
    if not ok:
        raise ToolError("nenhum navegador disponível no sistema")
    return {"opened": True, "url": url}

register(ToolSpec("open_url", open_url, _validate, risk="low", mutating=True,
                  summary="Abre um URL http(s) no navegador. Nunca chamada por iniciativa própria."))
