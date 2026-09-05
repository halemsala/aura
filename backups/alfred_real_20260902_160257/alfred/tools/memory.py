import os, re, threading, time, uuid
from .. import paths, util
from ..registry import ToolSpec, register
from ..validators import ValidationError, normalize

MEM_PATH = paths.DATA_ROOT / "memory.json"
MAX_ENTRIES, MAX_TEXT = 2000, 2000
_lock = threading.Lock()

PERSONAL_RE = re.compile(
    r"(?i)\b(o meu|a minha|meu nome|telefone|telem[oó]vel|e-?mail|morada|nascimento|contribuinte|iban)\b"
    r"|[\w.+-]+@[\w-]+\.[\w.]+|\b9\d{8}\b")

def _load() -> list:
    if not MEM_PATH.exists():
        return []
    try:
        return json_loads(MEM_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []

def json_loads(s):
    import json
    return json.loads(s)

def _save(entries: list):
    util.atomic_write_json(MEM_PATH, entries)


# ---------- remember ----------
def _v_remember(args) -> dict:
    args = args or {}
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValidationError("nota vazia")
    if len(text) > MAX_TEXT:
        raise ValidationError(f"nota excede {MAX_TEXT} caracteres")
    kind = args.get("kind") or ("commitment" if re.search(r"(?i)\b(amanh|próxim|próxim|tens de|tem de)\b", text) else "note")
    if kind not in ("note", "preference", "commitment"):
        kind = "note"
    return {"text": text, "kind": kind}

def remember(args, ctx) -> dict:
    a = _v_remember(args)
    personal = bool(PERSONAL_RE.search(a["text"]))
    if personal and not ctx.authorized:
        return {"saved": False, "dry_run": True, "personal": True,
                "nota": "dados pessoais: só guardo depois de 'AUTORIZO'"}
    with _lock:
        entries = _load()
        entries = entries[-(MAX_ENTRIES - 1):]
        e = {"id": uuid.uuid4().hex[:8], "ts": time.time(), "kind": a["kind"], "text": a["text"]}
        entries.append(e)
        _save(entries)
    return {"saved": True, "id": e["id"], "kind": e["kind"], "personal": personal}

register(ToolSpec("remember", remember, _v_remember, risk="medium", mutating=True,
                  summary="Guarda nota/preferência/compromisso (dados pessoais só após AUTORIZO)"))


# ---------- memory_search ----------
def _v_search(args) -> dict:
    return {"query": normalize(str((args or {}).get("query", "")))}

def memory_search(args, ctx) -> dict:
    q = _v_search(args)["query"]
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    res = []
    for e in _load():
        hay = normalize(e.get("text", ""))
        if not tokens or any(t in hay for t in tokens):
            res.append(e)
        if len(res) >= 20:
            break
    return {"results": res, "count": len(res)}

register(ToolSpec("memory_search", memory_search, _v_search, risk="low", mutating=False,
                  summary="Pesquisa na memória local (só leitura)"))


# ---------- memory_delete ----------
def _v_delete(args) -> dict:
    args = args or {}
    q, mid = str(args.get("query") or "").strip(), str(args.get("id") or "").strip()
    if not q and not mid:
        raise ValidationError("indica 'id' ou 'query'")
    return {"query": q, "id": mid}

def memory_delete(args, ctx) -> dict:
    a = _v_delete(args)
    with _lock:
        entries = _load()
        keep, removed = [], []
        for e in entries:
            hit = (a["id"] and e.get("id") == a["id"]) or \
                  (a["query"] and normalize(a["query"]) in normalize(e.get("text", "")))
            (removed.append(e) if hit else keep.append(e))
        if not ctx.authorized:
            return {"dry_run": True, "would_remove": len(removed),
                    "ids": [e["id"] for e in removed[:20]], "nota": "responde AUTORIZO para apagar"}
        _save(keep)
    return {"deleted": len(removed), "ids": [e["id"] for e in removed]}

register(ToolSpec("memory_delete", memory_delete, _v_delete, risk="medium", mutating=True,
                  summary="Apaga notas da memória (dry-run sem AUTORIZO)"))


# ---------- memory_export ----------
def _v_export(args) -> dict:
    return {}

def memory_export(args, ctx) -> dict:
    entries = _load()
    dest = paths.DATA_ROOT / f"memory-export-{time.strftime('%Y%m%d-%H%M%S')}.json"
    util.atomic_write_json(dest, entries)
    return {"exported": True, "path": str(dest), "count": len(entries)}

register(ToolSpec("memory_export", memory_export, _v_export, risk="low", mutating=True,
                  summary="Exporta memória para JSON local (sem upload)"))


# ---------- memory_clear ----------
def _v_clear(args) -> dict:
    return {}

def memory_clear(args, ctx) -> dict:
    with _lock:
        n = len(_load())
        if not ctx.authorized:
            return {"dry_run": True, "would_remove": n, "nota": "responde AUTORIZO para limpar tudo"}
        _save([])
    return {"cleared": True, "removed": n}

register(ToolSpec("memory_clear", memory_clear, _v_clear, risk="high", mutating=True, sensitive=True,
                  summary="Limpa toda a memória (ferramenta sensível: exige AUTORIZO + execution_allowed/token)"))
