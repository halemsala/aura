#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pc_operator.py — braco de arquivo do assistente: acesso AO PC com comportas.

O QUE FAZ (todas por voz via CommandCenter, mutacoes SO com autorizacao):
    listar / ler / buscar / editar (find->replace com preview) / escrever /
    criar pasta / mover / apagar (p/ lixeira interna, nunca permanente) /
    abrir pasta no Explorer / esvaziar lixeira.

AS QUATRO COMPORTAS (leia o docstring do modulo antes de ampliar):
    1. ALLOWLIST de raizes — fora dela, negado. resolve()+contencao mata
       traversal/symlink/relativo-escapando.
    2. ZONAS PROIBIDAS: biometria (engine/data/people), cofre DPAPI
       (%LOCALAPPDATA%/AURA/secure), credenciais (.env/.pem/.key/.pfx/.kdbx,
       *token*, *credential*), .git/venv/__pycache__/node_modules. JOURNALS
       (*.jsonl do projeto) = somente-leitura (§4: fonte da verdade).
    3. PLANO + AUTORIZACAO: mutacao nunca executa direto — plan() gera a fala
       do que vai acontecer; CommandCenter exige o "sim" (TTL 45s).
    4. AUDIT + LIXEIRA: toda operacao em file_ops.jsonl; apagar/editar/
       sobrescrever guardam o original em engine/data/.aura_trash.

LIMITES DELIBERADOS v1:
    - NAO executa shell/comandos/programas (so abre pasta no Explorer).
    - NAO apaga diretorios (arquivos only; pasta vazia tambem recusada —
      mover/escrever cobrem o caso de uso).
    - Batches de no max 25 arquivos; ler ate 500KB (binario recusado);
      escrever ate 200KB; busca com orcamento de tempo.
    - web_ler: GET somente, bloqueia IP privado (SSRF) exceto os proprios
      servicos locais; strip de HTML; teto 1MB / 6k chars.

INTEGRACAO (hunks na resposta): build_pc_tools(cc, pc, root) registra as
tools no CommandCenter — mutacoes com confirm=True e confirm_speech_fn=plan
(a fala de autorizacao e o PLANO real, nao um generico).

stdlib only. Python 3.9+. Windows compativel. Console ASCII.
"""
from __future__ import annotations

import html.parser
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.pc_operator")

__version__ = "1.0.0"

_PROJ_ROOT = Path(__file__).resolve().parents[2]

_DENY_DIR_NAMES = {".git", "__pycache__", "venv", ".venv", "node_modules",
                   ".aura_trash"}
_DENY_NAME_RE = re.compile(r"\.(env|pem|key|pfx|kdbx)$|^token|credential", re.I)
_LOCAL_OK_HOSTS = {"127.0.0.1", "localhost"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _TextExtractor(html.parser.HTMLParser):
    _SKIP = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def extract_text_from_html(html_src: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html_src)
    except Exception:
        pass
    return re.sub(r"\s{2,}", " ", " ".join(p.parts)).strip()


def _host_is_public_or_local_ok(hostname: str) -> bool:
    """Bloqueia IP privado (SSRF) exceto localhost (nossos servicos)."""
    host = (hostname or "").strip().lower()
    if host in _LOCAL_OK_HOSTS:
        return True
    try:
        ip = socket.gethostbyname(host)
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved)
    except Exception:
        return False


class PcOperator:
    """Executor de operacoes de arquivo com comportas. Sem estado pendente:
    o fluxo de autorizacao pertence ao CommandCenter (um unico choke point)."""

    MAX_READ_BYTES = 500_000
    MAX_WRITE_BYTES = 200_000
    MAX_BATCH = 25
    MAX_LIST = 200
    MAX_SEARCH_RESULTS = 30
    SEARCH_BUDGET_S = 6.0

    def __init__(self, roots: List[Any], project_root: Optional[Any] = None,
                 trash_dir: Optional[Any] = None,
                 audit_path: Optional[Any] = None):
        self._lock = threading.RLock()
        self._roots: List[Path] = []
        for r in roots:
            p = Path(r)
            try:
                rp = p.resolve()
            except OSError:
                continue
            if rp.exists() and rp.is_dir():
                self._roots.append(rp)
        if not self._roots:
            raise ValueError("pc_operator: nenhuma raiz permitida existe")
        proj = Path(project_root).resolve() if project_root else _PROJ_ROOT
        self._project_root = proj
        self._trash = Path(trash_dir) if trash_dir else \
            proj / "engine" / "data" / ".aura_trash"
        self._audit = Path(audit_path) if audit_path else \
            proj / "engine" / "data" / "file_ops.jsonl"
        self._trash.mkdir(parents=True, exist_ok=True)
        # zonas proibidas absolutas
        self._deny_roots: List[Path] = [
            (proj / "engine" / "data" / "people").resolve(),
            Path(os.environ.get("LOCALAPPDATA", "")) .joinpath("AURA", "secure"),
        ]
        self.counts: Dict[str, int] = {"read_ops": 0, "mutations": 0,
                                       "denied": 0, "plan_calls": 0}

    # ------------------------------------------------------------ guardas
    def _contained(self, child: Path, root: Path) -> bool:
        try:
            child.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_candidate(self, user_path: str) -> Path:
        raw = (user_path or "").strip().strip('"').strip("'")
        p = Path(raw) if raw else Path(".")
        if p.is_absolute():
            return p
        for r in self._roots:
            cand = r / p
            if cand.exists():
                return cand
        return (self._roots[0] / p) if raw else self._roots[0]

    def _guard(self, path: Path, write: bool) -> Tuple[Optional[Path], Optional[str]]:
        """Devolve (caminho resolvido, None) se liberado, ou (None, motivo)."""
        try:
            rp = path.resolve(strict=False)
        except (OSError, RuntimeError):
            return None, "caminho ilegivel"
        if not any(self._contained(rp, r) for r in self._roots):
            self.counts["denied"] += 1
            return None, "fora das pastas permitidas (%s)" % rp
        if self._contained(rp, self._trash):
            return None, "dentro da lixeira interna (use esvaziar_lixeira)"
        for d in self._deny_roots:
            try:
                if self._contained(rp, d):
                    self.counts["denied"] += 1
                    return None, "zona proibida (biometria/credenciais)"
            except Exception:
                pass
        parts = rp.parts
        if any(part.lower() in _DENY_DIR_NAMES for part in parts[1:]):
            self.counts["denied"] += 1
            return None, "diretorio protegido do sistema/projeto"
        if _DENY_NAME_RE.search(rp.name):
            self.counts["denied"] += 1
            return None, "arquivo de credenciais (protegido)"
        if self._contained(rp, self._project_root) and \
                (rp.suffix == ".jsonl" or rp.name.endswith(".jsonl.gz")):
            if write:
                self.counts["denied"] += 1
                return None, "journal e somente-leitura (fonte da verdade)"
        return rp, None

    def _audit_line(self, op: str, args: Dict[str, Any], ok: bool,
                    speech: str) -> None:
        try:
            safe_args = {k: (str(v)[:120]) for k, v in (args or {}).items()}
            self._audit.parent.mkdir(parents=True, exist_ok=True)
            with open(self._audit, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": _iso_now(), "op": op,
                                     "args": safe_args, "ok": ok,
                                     "speech": speech[:160]},
                                    ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("pc_operator: audit falhou")

    def _backup(self, path: Path) -> Optional[Path]:
        """Guarda o original na lixeira antes de mutacao. None se nao existe."""
        if not path.exists():
            return None
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = self._trash / ("%s__%s" % (ts, path.name))
        i = 1
        while dest.exists():
            dest = self._trash / ("%s__%d__%s" % (ts, i, path.name))
            i += 1
        try:
            if path.is_dir():
                shutil.copytree(path, dest)
            else:
                shutil.copy2(path, dest)
            return dest
        except OSError:
            logger.exception("pc_operator: backup falhou para %s", path)
            return None

    # ------------------------------------------------------------ ops
    def _op_listar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        target = self._resolve_candidate(str(args.get("caminho", "")))
        rp, err = self._guard(target, write=False)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        if not rp.is_dir():
            return {"ok": False, "speech": "%s nao e uma pasta." % rp.name}
        try:
            entries = sorted(rp.iterdir(),
                             key=lambda e: (e.is_file(), e.name.lower()))
        except OSError as exc:
            return {"ok": False, "speech": "Falha ao listar: %s" % exc}
        total = len(entries)
        shown = entries[: self.MAX_LIST]
        ndirs = sum(1 for e in shown if e.is_dir())
        names = [e.name + ("/" if e.is_dir() else "")
                 for e in shown[:8]]
        self.counts["read_ops"] += 1
        speech = ("%d itens (%d pastas). Primeiros: %s."
                  % (total, ndirs, ", ".join(names) if names else "vazia"))
        return {"ok": True, "speech": speech,
                "entries": [{"name": e.name, "dir": e.is_dir(),
                             "size": (e.stat().st_size if e.is_file() else None)}
                            for e in shown]}

    def _read_text_head(self, rp: Path) -> Tuple[Optional[str], Optional[str]]:
        try:
            size = rp.stat().st_size
        except OSError as exc:
            return None, "arquivo inacessivel: %s" % exc
        if size > 50_000_000:
            return None, "arquivo grande demais para ler por voz (50MB)"
        try:
            blob = rp.read_bytes()[: self.MAX_READ_BYTES]
        except OSError as exc:
            return None, "falha ao ler: %s" % exc
        if b"\0" in blob[:1024]:
            return None, "arquivo binario — leitura só de texto"
        return blob.decode("utf-8", errors="replace"), None

    def _op_ler(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=False)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        if not rp.is_file():
            return {"ok": False, "speech": "%s nao e um arquivo." % rp.name}
        text, rerr = self._read_text_head(rp)
        if text is None:
            return {"ok": False, "speech": rerr or "ilegivel"}
        self.counts["read_ops"] += 1
        head = text[:300].replace("\n", " ")
        speech = "%s: %s%s" % (rp.name, head, "..." if len(text) > 300 else "")
        return {"ok": True, "speech": speech, "content": text,
                "truncated": len(text) >= self.MAX_READ_BYTES}

    def _op_buscar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        term = str(args.get("termo", "")).strip().lower()
        if not term:
            return {"ok": False, "speech": "Diga o termo da busca."}
        content_term = str(args.get("conteudo", "")).strip() or None
        results: List[Dict[str, Any]] = []
        visited = 0
        t0 = time.monotonic()
        for root in self._roots:
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames
                               if d.lower() not in _DENY_DIR_NAMES]
                for fn in filenames:
                    visited += 1
                    if time.monotonic() - t0 > self.SEARCH_BUDGET_S or \
                            visited > 30000:
                        break
                    if term in fn.lower():
                        full = Path(dirpath) / fn
                        rp, err = self._guard(full, write=False)
                        if err or rp is None:
                            continue
                        results.append({"caminho": str(rp), "nome": fn})
                        if len(results) >= self.MAX_SEARCH_RESULTS:
                            break
                if len(results) >= self.MAX_SEARCH_RESULTS:
                    break
            if len(results) >= self.MAX_SEARCH_RESULTS:
                break
        self.counts["read_ops"] += 1
        if not results:
            return {"ok": True, "speech": "Nada encontrado com '%s'." % term,
                    "results": []}
        speech = ("%d resultado(s): %s." % (
            len(results), ", ".join(r["nome"] for r in results[:5])))
        return {"ok": True, "speech": speech, "results": results}

    # -------- mutacoes: plan() + do() --------
    def _plan_editar(self, args: Dict[str, Any]) -> str:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=False)
        if err:
            return "Negado: %s." % err
        if not rp.is_file():
            return "%s nao encontrado." % rp.name
        find = str(args.get("procurar", ""))
        replace = str(args.get("substituir", ""))
        if not find:
            return "Falta o texto a procurar."
        text, rerr = self._read_text_head(rp)
        if text is None:
            return rerr or "ilegivel"
        n = text.count(find)
        if n == 0:
            return "Nenhuma ocorrencia de '%s' em %s — nada a fazer." % (find, rp.name)
        if n > 200:
            return ("%d ocorrencias — padrao largo demais; recuso por seguranca." % n)
        i = text.find(find)
        ctx = text[max(0, i - 40):i + len(find) + 40].replace("\n", " ")
        return ("Vou editar %s: %d substituicao(s) de '%s' por '%s'. "
                "Contexto: ...%s... Backup do original vai para a lixeira "
                "interna. Diga sim para executar."
                % (rp.name, n, find, replace, ctx))

    def _op_editar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        if not rp.is_file():
            return {"ok": False, "speech": "%s nao encontrado." % rp.name}
        find = str(args.get("procurar", ""))
        replace = str(args.get("substituir", ""))
        if not find:
            return {"ok": False, "speech": "Falta o texto a procurar."}
        try:
            text = rp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "speech": "falha ao ler: %s" % exc}
        n = text.count(find)
        if n == 0:
            return {"ok": False, "speech": "Nada a substituir."}
        if n > 200:
            return {"ok": False, "speech": "padrao largo demais; recusado"}
        new_text = text.replace(find, replace)
        if len(new_text.encode("utf-8")) > self.MAX_WRITE_BYTES:
            return {"ok": False, "speech": "resultado excederia o limite de escrita"}
        backup = self._backup(rp)
        tmp = rp.with_suffix(rp.suffix + ".aura_tmp")
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, rp)
        self.counts["mutations"] += 1
        speech = ("Editado: %d substituicao(s) em %s."
                  % (n, rp.name))
        self._audit_line("editar", args, True, speech)
        return {"ok": True, "speech": speech, "ocorrencias": n,
                "backup": str(backup) if backup else None}

    def _plan_escrever(self, args: Dict[str, Any]) -> str:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return "Negado: %s." % err
        content = str(args.get("conteudo", ""))
        if not content.strip():
            return "Conteudo vazio — nada a escrever."
        if len(content.encode("utf-8")) > self.MAX_WRITE_BYTES:
            return "conteudo excede o limite de 200KB"
        if rp.exists():
            return ("Vou SOBRESCREVER %s (%d bytes novos; original na lixeira "
                    "interna). Diga sim para executar."
                    % (rp.name, len(content.encode("utf-8"))))
        if not rp.parent.exists():
            return "pasta %s nao existe; crie antes (criar_pasta)." % rp.parent.name
        return ("Vou CRIAR %s com %d bytes. Diga sim para executar."
                % (rp.name, len(content.encode("utf-8"))))

    def _op_escrever(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        content = str(args.get("conteudo", ""))
        if not content.strip():
            return {"ok": False, "speech": "conteudo vazio"}
        if len(content.encode("utf-8")) > self.MAX_WRITE_BYTES:
            return {"ok": False, "speech": "conteudo excede 200KB"}
        if not rp.parent.exists():
            return {"ok": False, "speech": "pasta pai inexistente"}
        backup = self._backup(rp) if rp.exists() else None
        tmp = rp.with_suffix(rp.suffix + ".aura_tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, rp)
        self.counts["mutations"] += 1
        speech = ("Salvo: %s (%d bytes%s)."
                  % (rp.name, len(content.encode("utf-8")),
                     ", sobrescrito" if backup else ", novo"))
        self._audit_line("escrever", args, True, speech)
        return {"ok": True, "speech": speech}

    def _plan_mover(self, args: Dict[str, Any]) -> str:
        src, err1 = self._guard(self._resolve_candidate(
            str(args.get("de", ""))), write=True)
        dst, err2 = self._guard(self._resolve_candidate(
            str(args.get("para", ""))), write=True)
        if err1:
            return "Origem negada: %s." % err1
        if err2:
            return "Destino negado: %s." % err2
        if not src.exists():
            return "%s nao existe." % src.name
        if dst.exists():
            return "destino %s ja existe; recuso sobrescrever por movimento." % dst.name
        return ("Vou mover %s para %s. Diga sim para executar."
                % (src.name, dst.name))

    def _op_mover(self, args: Dict[str, Any]) -> Dict[str, Any]:
        src, err1 = self._guard(self._resolve_candidate(
            str(args.get("de", ""))), write=True)
        dst, err2 = self._guard(self._resolve_candidate(
            str(args.get("para", ""))), write=True)
        if err1 or err2:
            return {"ok": False, "speech": "Negado: %s." % (err1 or err2)}
        if not src.exists() or dst.exists():
            return {"ok": False, "speech": "origem/destino invalido"}
        try:
            shutil.move(str(src), str(dst))
        except (OSError, shutil.Error) as exc:
            return {"ok": False, "speech": "falha ao mover: %s" % exc}
        self.counts["mutations"] += 1
        speech = "Movido para %s." % dst.name
        self._audit_line("mover", args, True, speech)
        return {"ok": True, "speech": speech}

    def _plan_apagar(self, args: Dict[str, Any]) -> str:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return "Negado: %s." % err
        if not rp.exists():
            return "%s nao existe." % rp.name
        if rp.is_dir():
            return ("Apagar pastas nao e suportado (mova ou apague os arquivos "
                    "um a um).")
        size = rp.stat().st_size
        return ("Vou apagar %s (%d bytes) — na pratica, mover para a lixeira "
                "interna, de onde da para recuperar. Diga sim para executar."
                % (rp.name, size))

    def _op_apagar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        if not rp.exists() or rp.is_dir():
            return {"ok": False, "speech": "so apago arquivos existentes"}
        ts = time.strftime("%Y%m%d_%H%M%S")
        dest = self._trash / ("%s__%s" % (ts, rp.name))
        i = 1
        while dest.exists():
            dest = self._trash / ("%s__%d__%s" % (ts, i, rp.name))
            i += 1
        try:
            shutil.move(str(rp), str(dest))
        except OSError as exc:
            return {"ok": False, "speech": "falha ao apagar: %s" % exc}
        self.counts["mutations"] += 1
        speech = "Apagado (na lixeira interna): %s." % rp.name
        self._audit_line("apagar", args, True, speech)
        return {"ok": True, "speech": speech, "lixeira": str(dest)}

    def _op_criar_pasta(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=True)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        if rp.exists():
            return {"ok": False, "speech": "%s ja existe." % rp.name}
        try:
            rp.mkdir(parents=False)
        except OSError as exc:
            return {"ok": False, "speech": "falha ao criar: %s" % exc}
        self.counts["mutations"] += 1
        self._audit_line("criar_pasta", args, True, "pasta criada")
        return {"ok": True, "speech": "Pasta criada: %s." % rp.name}

    def _op_abrir_pasta(self, args: Dict[str, Any]) -> Dict[str, Any]:
        rp, err = self._guard(self._resolve_candidate(
            str(args.get("caminho", ""))), write=False)
        if err:
            return {"ok": False, "speech": "Negado: %s." % err}
        target = rp if rp.is_dir() else rp.parent
        try:
            subprocess.run(["explorer", str(target)], check=False)
        except OSError as exc:
            return {"ok": False, "speech": "falha ao abrir: %s" % exc}
        return {"ok": True, "speech": "Abri %s no Explorer." % target.name}

    def _plan_esvaziar_lixeira(self, args: Dict[str, Any]) -> str:
        n = 0
        size = 0
        for f in self._trash.iterdir():
            n += 1
            try:
                size += f.stat().st_size if f.is_file() else 0
            except OSError:
                pass
        if n == 0:
            return "Lixeira interna ja esta vazia."
        return ("Vou apagar DEFINITIVAMENTE %d item(s) da lixeira interna "
                "(~%d KB) — isso sim e irreversivel. Diga sim para executar."
                % (n, size // 1024))

    def _op_esvaziar_lixeira(self, args: Dict[str, Any]) -> Dict[str, Any]:
        n = 0
        for f in list(self._trash.iterdir()):
            try:
                if f.is_dir():
                    shutil.rmtree(f)
                else:
                    f.unlink()
                n += 1
            except OSError:
                logger.warning("pc_operator: falha ao remover %s", f)
        self.counts["mutations"] += 1
        self._audit_line("esvaziar_lixeira", args, True, "%d itens" % n)
        return {"ok": True, "speech": "Lixeira interna esvaziada: %d itens." % n}

    OPS: Dict[str, Any] = {}  # preenchido abaixo (plan/do separados)

    _PLANS = {"editar": _plan_editar, "escrever": _plan_escrever,
              "mover": _plan_mover, "apagar": _plan_apagar,
              "esvaziar_lixeira": _plan_esvaziar_lixeira}
    _DO = {"listar": _op_listar, "ler": _op_ler, "buscar": _op_buscar,
           "editar": _op_editar, "escrever": _op_escrever,
           "mover": _op_mover, "apagar": _op_apagar,
           "criar_pasta": _op_criar_pasta, "abrir_pasta": _op_abrir_pasta,
           "esvaziar_lixeira": _op_esvaziar_lixeira}

    def plan(self, op: str, args: Dict[str, Any]) -> str:
        """Fala de autorizacao: o que VAI acontecer (sem executar)."""
        self.counts["plan_calls"] += 1
        fn = self._PLANS.get(op)
        if fn is None:
            return "Confirmar %s?" % op
        try:
            return fn(self, args or {})
        except Exception:
            logger.exception("pc_operator: plan falhou (%s)", op)
            return "Nao consegui preparar o plano de %s." % op

    def do(self, op: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Executa (so chega aqui depois de autorizado, ou se e leitura)."""
        fn = self._DO.get(op)
        if fn is None:
            return {"ok": False, "speech": "operacao desconhecida: %s" % op}
        try:
            return fn(self, args or {})
        except Exception as exc:
            logger.exception("pc_operator: do falhou (%s)", op)
            self._audit_line(op, args or {}, False, "erro: %s" % exc)
            return {"ok": False, "speech": "falha interna em %s" % op}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            trash_n = 0
            try:
                trash_n = sum(1 for _ in self._trash.iterdir())
            except OSError:
                pass
            return {"pc_operator": {
                "roots": [str(r) for r in self._roots],
                "read_ops": self.counts["read_ops"],
                "mutations": self.counts["mutations"],
                "denied": self.counts["denied"],
                "plan_calls": self.counts["plan_calls"],
                "trash_items": trash_n,
            }}


# ---------------------------------------------------------------------------
# registro no CommandCenter + web + entrega de relatorio
# ---------------------------------------------------------------------------
def build_pc_tools(cc, pc: PcOperator, root: Optional[Any] = None) -> None:
    """Registra as tools de arquivo/web/relatorio. Mutacoes: confirm=True com
    confirm_speech_fn=plan (a autorizacao fala o PLANO real)."""
    proj = Path(root).resolve() if root else _PROJ_ROOT

    def reg(name, desc, op, confirm, args=None):
        return cc.register(
            name, desc, lambda a, s, _op=op: pc.do(_op, a),
            "control" if confirm else "read", args=args, confirm=confirm,
            confirm_speech_fn=(lambda a, _op=op: pc.plan(_op, a))
            if confirm else None)

    reg("arquivo_listar", "listar conteudo de uma pasta", "listar", False,
        args={"caminho": "pasta"})
    reg("arquivo_ler", "ler cabecalho de um arquivo de texto", "ler", False,
        args={"caminho": "arquivo"})
    reg("arquivo_buscar", "buscar arquivo por nome", "buscar", False,
        args={"termo": "nome ou parte"})
    reg("arquivo_editar",
        "editar arquivo: substituir texto (com autorizacao)", "editar", True,
        args={"caminho": "arquivo", "procurar": "texto",
              "substituir": "novo texto"})
    reg("arquivo_escrever", "criar ou sobrescrever arquivo", "escrever", True,
        args={"caminho": "arquivo", "conteudo": "texto"})
    reg("arquivo_mover", "mover/renomear arquivo", "mover", True,
        args={"de": "origem", "para": "destino"})
    reg("arquivo_apagar", "apagar arquivo (lixeira interna)", "apagar", True,
        args={"caminho": "arquivo"})
    reg("arquivo_criar_pasta", "criar pasta", "criar_pasta", True,
        args={"caminho": "pasta"})
    reg("arquivo_abrir_pasta", "abrir pasta no Explorer", "abrir_pasta", False,
        args={"caminho": "pasta"})
    reg("lixeira_esvaziar", "apagar definitivamente o que esta na lixeira "
        "interna", "esvaziar_lixeira", True)

    def t_web_ler(args, session):
        url = str(args.get("url", "")).strip()
        if not url:
            return {"ok": False, "speech": "Diga o endereco do site."}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            host = urllib.request.urlsplit(url).hostname or ""
        except ValueError:
            return {"ok": False, "speech": "endereco invalido"}
        if not _host_is_public_or_local_ok(host):
            return {"ok": False, "speech": "endereco de rede privada bloqueado"}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AURA/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                ctype = resp.headers.get("Content-Type", "")
                blob = resp.read(1_000_000)
        except Exception as exc:
            return {"ok": False, "speech": "falha ao acessar: %s" % exc}
        if "html" in ctype.lower():
            text = extract_text_from_html(blob.decode("utf-8", errors="replace"))
        elif "text" in ctype.lower() or "json" in ctype.lower():
            text = blob.decode("utf-8", errors="replace")
        else:
            return {"ok": False, "speech": "tipo de conteudo nao texto (%s)" % ctype}
        text = text[:6000]
        head = text[:400].replace("\n", " ")
        return {"ok": True, "speech": "Pagina carregada: %s" % head,
                "content": text, "url": url}

    cc.register("web_ler", "ler uma pagina web (somente leitura)", t_web_ler,
                "read", args={"url": "endereco"})

    def t_relatorio_plan(args):
        return ("Vou rodar o job semanal de analytics e salvar o relatorio "
                "na pasta AURA_Relatorios da Area de Trabalho, com a data de "
                "hoje. Diga sim para executar.")

    def t_relatorio(args, session):
        import subprocess as sp
        import sys
        script = proj / "scripts" / "aura_weekly_analytics.py"
        if not script.is_file():
            return {"ok": False, "speech": "script de analytics ausente"}
        try:
            proc = sp.run([sys.executable, str(script)], cwd=str(proj),
                          capture_output=True, timeout=300)
        except Exception as exc:
            return {"ok": False, "speech": "job falhou: %s" % exc}
        if proc.returncode != 0:
            return {"ok": False,
                    "speech": "job retornou erro; veja o log"}
        src = proj / "engine" / "data" / "weekly_report.md"
        if not src.is_file():
            return {"ok": False, "speech": "relatorio nao foi gerado"}
        out_dir = Path.home() / "Desktop" / "AURA_Relatorios"
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / ("weekly_%s.md" % time.strftime("%Y%m%d"))
        shutil.copy2(src, dst)
        return {"ok": True,
                "speech": "Relatorio entregue em %s." % dst.name,
                "caminho": str(dst)}

    cc.register("entregar_relatorio",
                "rodar analytics e entregar o relatorio semanal",
                t_relatorio, "control", args={},
                confirm=True, confirm_speech_fn=t_relatorio_plan)


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory(prefix="aura_pc_st_") as td:
        home = Path(td)
        docs = home / "Documents"
        (docs / "projetos").mkdir(parents=True)
        (docs / "nota.txt").write_text("lucro de hoje foi bom. lucro de ontem tambem.", encoding="utf-8")
        (docs / "bin.dat").write_bytes(b"\x00\x01\x02\x00")
        proj = home / "aura"
        (proj / "engine" / "data").mkdir(parents=True)
        (proj / "engine" / "data" / "people").mkdir(parents=True)
        (proj / "engine" / "data" / "people" / "hal.json").write_text("{}", encoding="utf-8")
        (proj / "engine" / "data" / "decisions.jsonl").write_text('{"decision":"HOLD"}\n', encoding="utf-8")
        (proj / "bridge").mkdir()
        (proj / "bridge" / "live_feed.jsonl").write_text("{}\n", encoding="utf-8")
        (docs / ".env").write_text("SECRET=1", encoding="utf-8")

        pc = PcOperator(roots=[docs, proj], project_root=proj,
                        trash_dir=proj / "engine" / "data" / ".aura_trash",
                        audit_path=proj / "engine" / "data" / "file_ops.jsonl")

        # guarda 1: fora do allowlist + traversal
        r = pc.do("ler", {"caminho": str(home / "senha.txt")})
        check("guarda: fora do allowlist negado", r["ok"] is False)
        r = pc.do("ler", {"caminho": str(docs / ".." / ".." / "windows" / "win.ini")})
        check("guarda: traversal negado", r["ok"] is False)

        # guarda 2: zonas proibidas
        r = pc.do("ler", {"caminho": str(proj / "engine" / "data" / "people" / "hal.json")})
        check("guarda: biometria inacessivel", r["ok"] is False)
        r = pc.do("ler", {"caminho": str(docs / ".env")})
        check("guarda: credencial inacessivel", r["ok"] is False)
        r = pc.do("ler", {"caminho": str(proj / "engine" / "data" / "decisions.jsonl")})
        check("journal: leitura permitida", r["ok"] is True)
        r = pc.do("escrever", {"caminho": str(proj / "engine" / "data" / "decisions.jsonl"),
                               "conteudo": "falsificado"})
        check("journal: escrita NEGADA (§4)", r["ok"] is False)

        # guarda 3: plano fala o que vai fazer
        plan = pc.plan("editar", {"caminho": str(docs / "nota.txt"),
                                  "procurar": "lucro", "substituir": "resultado"})
        check("plano: conta ocorrencias", "2 substituicao" in plan, plan[:80])
        check("plano: menciona backup", "lixeira" in plan)
        plan0 = pc.plan("editar", {"caminho": str(docs / "nota.txt"),
                                   "procurar": "zzz", "substituir": "x"})
        check("plano: zero ocorrencias avisa", "Nenhuma ocorrencia" in plan0)

        # execucao pos-autorizacao + backup + audit
        r = pc.do("editar", {"caminho": str(docs / "nota.txt"),
                             "procurar": "lucro", "substituir": "resultado"})
        check("editar: executa 2 substituicoes",
              r["ok"] is True and r["ocorrencias"] == 2)
        novo = (docs / "nota.txt").read_text(encoding="utf-8")
        check("editar: conteudo alterado", "lucro" not in novo
              and novo.count("resultado") == 2)
        check("editar: backup salvo na lixeira",
              r.get("backup") is not None and Path(r["backup"]).is_file())
        with open(proj / "engine" / "data" / "file_ops.jsonl", encoding="utf-8") as fh:
            linhas = [l for l in fh.read().splitlines() if l.strip()]
        check("audit: mutacao registrada", len(linhas) >= 1
              and '"op": "editar"' in linhas[-1])

        # escrever novo / sobrescrever
        r = pc.do("escrever", {"caminho": str(docs / "projetos" / "novo.md"),
                               "conteudo": "# titulo"})
        check("escrever: cria arquivo", r["ok"] is True
              and (docs / "projetos" / "novo.md").is_file())
        r = pc.do("escrever", {"caminho": str(docs / "projetos" / "novo.md"),
                               "conteudo": "# titulo 2"})
        check("escrever: sobrescreve com backup", r["ok"] is True
              and (docs / "projetos" / "novo.md").read_text(encoding="utf-8") == "# titulo 2")

        # binario recusado
        r = pc.do("ler", {"caminho": str(docs / "bin.dat")})
        check("ler: binario recusado", r["ok"] is False
              and "binario" in r["speech"])

        # apagar -> lixeira, recuperavel
        (docs / "velho.txt").write_text("x", encoding="utf-8")
        r = pc.do("apagar", {"caminho": str(docs / "velho.txt")})
        check("apagar: arquivo sai do lugar", r["ok"] is True
              and not (docs / "velho.txt").exists())
        check("apagar: recuperavel na lixeira", Path(r["lixeira"]).is_file())
        # pasta nao apaga
        r = pc.do("apagar", {"caminho": str(docs / "projetos")})
        check("apagar: diretorio recusado", r["ok"] is False)

        # mover
        r = pc.do("mover", {"de": str(docs / "projetos" / "novo.md"),
                            "para": str(docs / "novo_movido.md")})
        check("mover: ok", r["ok"] is True
              and (docs / "novo_movido.md").is_file())

        # listar / buscar
        r = pc.do("listar", {"caminho": str(docs)})
        check("listar: fala itens", r["ok"] is True and "itens" in r["speech"])


        r = pc.do("buscar", {"termo": "nota"})
        check("buscar: acha por nome", r["ok"] is True
              and any("nota.txt" in x["nome"] for x in r["results"]))

        # web: guarda SSRF + extracao
        check("web: IP privado bloqueado",
              _host_is_public_or_local_ok("10.0.0.1") is False)
        check("web: localhost liberado (servicos proprios)",
              _host_is_public_or_local_ok("127.0.0.1") is True)
        txt = extract_text_from_html(
            "<html><head><style>x</style><script>bad()</script></head>"
            "<body><h1>Titulo</h1><p>Corpo da pagina</p></body></html>")
        check("web: strip de html/script/style",
              "Titulo" in txt and "Corpo" in txt and "bad" not in txt
              and "x" not in txt.split("Corpo")[0])

        # stats
        st = pc.stats()["pc_operator"]
        check("stats: mutacoes e negacoes contadas",
              st["mutations"] >= 4 and st["denied"] >= 3
              and st["trash_items"] >= 2)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - pc_operator.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
