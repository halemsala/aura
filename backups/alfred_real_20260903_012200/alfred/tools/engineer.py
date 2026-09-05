"""Capacidade de engenharia no Aura: ler código, procurar, processar inbox, pedir ajuda.

Só C:\\aura. Apagar e pastas do Windows continuam bloqueados. Mutável = AUTORIZO.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

from .. import paths
from ..registry import ToolSpec, register
from ..validators import ValidationError
from . import tooling

INBOX = paths.DATA_ROOT / "inbox"
SKIP_DIRS = {".git", "venv", "engine\\venv", "node_modules", "__pycache__", "backups",
             "desktop\\bin", "desktop\\publish", ".pytest_cache"}
ALLOWED_UPLOAD = {
    ".txt", ".md", ".json", ".py", ".zip", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".wav", ".mp3", ".ogg", ".webm", ".pdf", ".csv", ".bat", ".ps1", ".yml", ".yaml",
    ".html", ".css", ".js", ".toml", ".docx",
}
MAX_BYTES = 25 * 1024 * 1024
INBOX.mkdir(parents=True, exist_ok=True)


def _v0(args) -> dict:
    return {}


def _under_aura(p: Path) -> bool:
    try:
        p.resolve().relative_to(paths.PROJECT_ROOT.resolve())
        return True
    except ValueError:
        return False


def _v_search(args) -> dict:
    q = str((args or {}).get("query") or "").strip()
    if not q or len(q) > 120:
        raise ValidationError("query 1-120 chars")
    return {"query": q}


def search_aura_code(args, ctx) -> dict:
    q = _v_search(args)["query"].casefold()
    hits = []
    root = paths.PROJECT_ROOT
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root).as_posix().casefold()
        if any(s in rel for s in ("venv", "node_modules", "__pycache__", ".git", "backups", "bin/release")):
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in {".git", "venv", "node_modules", "__pycache__"}]
        for name in filenames:
            if not name.endswith((".py", ".md", ".json", ".bat", ".yml", ".yaml")):
                continue
            p = Path(dirpath) / name
            try:
                if p.stat().st_size > 400_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if q not in text.casefold() and q not in name.casefold():
                continue
            line_no = 1
            snippet = ""
            for i, line in enumerate(text.splitlines(), 1):
                if q in line.casefold():
                    line_no, snippet = i, line.strip()[:180]
                    break
            hits.append({"path": str(p), "line": line_no, "snippet": snippet})
            if len(hits) >= 20:
                return {"query": q, "hits": hits, "nota": "máx 20 — pede um path concreto para eu ler"}
    return {"query": q, "hits": hits, "count": len(hits)}


register(ToolSpec("search_aura_code", search_aura_code, _v_search, risk="low", mutating=False,
                  summary="Procura texto no código do Aura (só C:\\aura, sem venv)."))


def _v_read(args) -> dict:
    raw = str((args or {}).get("path") or "").strip()
    if not raw:
        raise ValidationError("path vazio")
    p = Path(raw)
    if not p.is_absolute():
        p = paths.PROJECT_ROOT / p
    p = p.resolve()
    if not _under_aura(p):
        raise ValidationError("só leio código dentro de C:\\aura")
    if p.suffix.lower() not in {".py", ".md", ".json", ".txt", ".bat", ".yml", ".yaml", ".toml"}:
        raise ValidationError("extensão não permitida para leitura de código")
    if not p.is_file() or p.stat().st_size > 200_000:
        raise ValidationError("ficheiro inexistente ou >200 KB")
    return {"path": p}


def read_aura_source(args, ctx) -> dict:
    p = _v_read(args)["path"]
    return {"path": str(p), "content": p.read_text(encoding="utf-8", errors="replace")[:80000]}


register(ToolSpec("read_aura_source", read_aura_source, _v_read, risk="low", mutating=False,
                  summary="Lê um ficheiro de código do Aura (não Windows)."))


def _v_ingest(args) -> dict:
    raw = str((args or {}).get("path") or "").strip()
    if not raw:
        raise ValidationError("path do ficheiro da inbox")
    p = Path(raw)
    if not p.is_absolute():
        p = INBOX / p
    p = p.resolve()
    if not (_under_aura(p) and (str(p).casefold().startswith(str(INBOX.resolve()).casefold())
                                or str(p).casefold().startswith(str(paths.STAGING_DIR.resolve()).casefold()))):
        raise ValidationError("só processo ficheiros da inbox Alfred")
    if p.suffix.lower() not in ALLOWED_UPLOAD:
        raise ValidationError(f"formato não suportado: {p.suffix}")
    if not p.is_file() or p.stat().st_size > MAX_BYTES:
        raise ValidationError("ficheiro em falta ou >25 MB")
    return {"path": p}


def ingest_inbox(args, ctx) -> dict:
    p = _v_ingest(args)["path"]
    ext = p.suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return {"ok": True, "kind": "image", "path": str(p), "size": p.stat().st_size,
                "nota": "Imagem guardada. qwen3:8b é texto: descreve o que queres que eu faça com ela."}
    if ext in {".wav", ".mp3", ".ogg", ".webm"}:
        return {"ok": True, "kind": "audio", "path": str(p),
                "nota": "Áudio na inbox. Clica Falar no chat ou diz AUTORIZO para transcrever no Whisper."}
    if ext in {".txt", ".md", ".json", ".csv", ".yml", ".yaml", ".toml", ".html", ".css", ".js"}:
        text = p.read_text(encoding="utf-8", errors="replace")[:80000]
        return {"ok": True, "kind": "text", "path": str(p), "chars": len(text),
                "preview": text[:2500], "nota": "Li o texto. Diz o que instalar ou alterar (AUTORIZO)."}
    if ext == ".py":
        report = tooling.review_tool({"path": str(p)}, ctx)
        return {"ok": True, "kind": "python_tool", "path": str(p), "review": report,
                "nota": "Revisão feita. AUTORIZO e 'Alfred, instala esta ferramenta' para gravar o plugin."}
    if ext == ".zip":
        dest = paths.STAGING_DIR / p.stem
        dest.mkdir(parents=True, exist_ok=True)
        names = []
        with zipfile.ZipFile(p) as zf:
            for info in zf.infolist()[:80]:
                if info.is_dir() or ".." in info.filename.replace("\\", "/"):
                    continue
                names.append(info.filename)
            if not ctx.dry():
                zf.extractall(dest)
        pys = [n for n in names if n.lower().endswith(".py")]
        return {"ok": True, "kind": "zip", "path": str(p), "extracted_to": str(dest),
                "files": names[:40], "python_files": pys,
                "nota": "ZIP na staging. AUTORIZO + instala ferramenta para cada .py aprovado."}
    if ext in {".bat", ".ps1"}:
        return {"ok": True, "kind": "script", "path": str(p),
                "nota": "Script recebido. Não executo .bat/.ps1 automaticamente. Diz o que queres que eu faça."}
    if ext == ".pdf":
        return {"ok": True, "kind": "pdf", "path": str(p), "size": p.stat().st_size,
                "nota": "PDF guardado. Extrai texto à mão ou pede-me para o abrir depois de instalar um leitor."}
    return {"ok": True, "kind": "other", "path": str(p)}


register(ToolSpec("ingest_inbox", ingest_inbox, _v_ingest, risk="medium", mutating=True,
                  summary="Processa um ficheiro enviado no chat (inbox). ZIP/py exigem AUTORIZO para instalar."))


def list_inbox(args, ctx) -> dict:
    items = []
    for p in sorted(INBOX.glob("*")):
        if p.is_file():
            items.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    return {"inbox": str(INBOX), "count": len(items), "items": items[:50]}


register(ToolSpec("list_inbox", list_inbox, _v0, risk="low", mutating=False,
                  summary="Lista ficheiros enviados no chat (inbox)."))


def request_user_help(args, ctx) -> dict:
    need = str((args or {}).get("need") or "").strip()[:400]
    steps = str((args or {}).get("steps") or "").strip()[:800]
    return {
        "ok": True,
        "need": need or "preciso da tua acção",
        "steps": steps or "confirma AUTORIZO ou faz o passo no Windows que eu não posso (UAC, loja, login).",
        "nota": "Eu não mexo em C:\\Windows nem apago sem AUTORIZO. Se faltar permissão de admin, és tu.",
    }


register(ToolSpec("request_user_help", request_user_help, _v0, risk="low", mutating=False,
                  summary="Quando o Alfred precisa que o utilizador faça um passo (UAC, loja, AUTORIZO)."))
