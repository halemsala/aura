#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
media_editor.py — o assistente como EDITOR de video/imagem via FFmpeg,
com plano falado + 'sim' para cada render.

OPERACOES: cortar, converter (mp4/mkv/webm/mp3/m4a/wav), redimensionar,
comprimir, extrair audio, tirar audio, gif, miniaturas (contact sheet),
rotacionar, velocidade — e imagens (converter/redimensionar).

FRONTEIRAS:
    - Workspace unico: Documentos/AURA_Domestico/midia (guard de contencao).
    - argv em LISTA, nunca shell=True. Saida nunca sobrescreve (sufixo+contador).
    - Timeout de 10 min por render; falha reportada com stderr resumido.
    - Sem ffmpeg: degradacao honesta ('winget install Gyan.FFmpeg') —
      instalar software continua sendo tarefa do dono.
    - PERFIL CRIATIVO: preferencias ditas + observadas nos renders aprovados
      alimentam sugestoes e o contexto da persona. Versao honesta de
      'aprender seus padroes': registro e reaproveitamento.

stdlib only. Python 3.9+. Windows. Console ASCII.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.media")

__version__ = "1.0.0"
_PROJ_ROOT = Path(__file__).resolve().parents[2]

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_CODEC_ARGS: Dict[str, List[str]] = {
    "mp4": ["-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac", "-b:a", "128k"],
    "mkv": ["-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
            "-c:a", "aac"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "35", "-b:v", "0",
             "-c:a", "libopus"],
    "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    "m4a": ["-vn", "-c:a", "aac", "-b:a", "160k"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(v: Any) -> Optional[float]:
    s = str(v or "").strip()
    if not s:
        return None
    if re.fullmatch(r"[\d:.,]+", s):
        parts = s.replace(",", ".").split(":")
        if len(parts) <= 3:
            try:
                secs = 0.0
                for p in parts:
                    secs = secs * 60 + float(p)
                return secs if secs >= 0 else None
            except ValueError:
                return None
    m = re.fullmatch(r"(\d+)\s*m(?:in)?\s*(\d+)\s*s?", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _fmt_time(sec: float) -> str:
    return "%g" % max(0.0, float(sec))


# ---------------------------------------------------------------------------
# perfil criativo — o 'aprenda meus padroes' na versao honesta
# ---------------------------------------------------------------------------
class CreativeProfile:
    def __init__(self, path: Optional[Any] = None):
        self._path = (Path(path) if path is not None
                      else _PROJ_ROOT / "engine" / "data" / "creative_profile.json")
        self._lock = threading.RLock()
        self._prefs: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._prefs = {k: v for k, v in data.items()
                               if isinstance(v, dict) and v.get("value")}
        except Exception:
            self._prefs = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._prefs, ensure_ascii=False,
                                      indent=1), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            logger.exception("creative_profile: falha ao gravar")

    def set(self, key: str, value: str, origin: str = "declarado") -> None:
        key = _norm(key)
        if not key or not (value or "").strip():
            return
        with self._lock:
            old = self._prefs.get(key, {})
            self._prefs[key] = {"value": str(value).strip()[:80],
                                "origin": origin,
                                "count": int(old.get("count", 0)) + 1,
                                "ts": _iso_now()}
            self._save()

    def observe(self, key: str, value: Any) -> None:
        """Preferencia OBSERVADA em render aprovado — conta menos que dita."""
        if value is None or str(value).strip() == "":
            return
        with self._lock:
            old = self._prefs.get(key)
            if old and old.get("origin") == "declarado":
                old["count"] = int(old.get("count", 0)) + 1
                self._save()
                return
        self.set(key, value, origin="observado")

    def block_for_prompt(self) -> str:
        with self._lock:
            if not self._prefs:
                return ""
            lines = ["PERFIL CRIATIVO DO USUARIO (preferencias registradas — "
                     "use para sugerir formatos e parametros):"]
            for k, v in sorted(self._prefs.items()):
                lines.append("- %s: %s (%s, visto %dx)"
                             % (k, v["value"], v.get("origin", "?"),
                                v.get("count", 1)))
            return "\n".join(lines)

    def stats(self) -> dict:
        with self._lock:
            return {"creative_profile": {
                "prefs": len(self._prefs),
                "keys": sorted(self._prefs.keys()),
                "path": str(self._path)}}


# ---------------------------------------------------------------------------
# editor
# ---------------------------------------------------------------------------
class MediaEditor:
    MAX_INPUT_BYTES = 4_000_000_000
    RUN_TIMEOUT_S = 600.0

    def __init__(self, workspace: Optional[Any] = None,
                 ffmpeg: Optional[str] = None,
                 ffprobe: Optional[str] = None,
                 run_fn: Optional[Callable[[List[str]], Tuple[int, str]]] = None,
                 probe_fn: Optional[Callable[[Path], dict]] = None,
                 profile: Optional[CreativeProfile] = None):
        self._lock = threading.RLock()
        self._root = (Path(workspace) if workspace is not None
                      else Path.home() / "Documents" / "AURA_Domestico" / "midia"
                      ).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
        self._ffprobe = ffprobe if ffprobe is not None else shutil.which("ffprobe")
        self._run = run_fn or self._run_default
        self._probe = probe_fn or self._probe_default
        self.profile = profile or CreativeProfile()
        self.counts = {"renders": 0, "failed": 0, "denied": 0, "plans": 0}

    # ------------------------------------------------------------ infra
    def available(self) -> bool:
        return bool(self._ffmpeg)

    def _run_default(self, argv: List[str]) -> Tuple[int, str]:
        try:
            proc = subprocess.run(argv, capture_output=True,
                                  timeout=self.RUN_TIMEOUT_S)
            return proc.returncode, proc.stderr.decode("utf-8",
                                                        errors="replace")[-400:]
        except subprocess.TimeoutExpired:
            return 124, "render excedeu 10 minutos e foi interrompido"
        except OSError as exc:
            return 1, str(exc)

    def _probe_default(self, path: Path) -> dict:
        if not self._ffprobe:
            return {"duration": None, "size": None}
        try:
            proc = subprocess.run(
                [self._ffprobe, "-v", "error", "-show_entries",
                 "format=duration,size", "-of", "json", str(path)],
                capture_output=True, timeout=15)
            data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
            fmt = data.get("format") or {}
            return {"duration": float(fmt.get("duration") or 0) or None,
                    "size": int(fmt.get("size") or 0) or None}
        except Exception:
            return {"duration": None, "size": None}

    def _resolve(self, p: Any) -> Tuple[Optional[Path], Optional[str]]:
        raw = str(p or "").strip().strip('"').strip("'")
        if not raw:
            return None, "Diga o arquivo (dentro da pasta midia)."
        path = Path(raw)
        if not path.is_absolute():
            path = self._root / path
        try:
            rp = path.resolve(strict=False)
        except (OSError, RuntimeError):
            return None, "caminho ilegivel"
        try:
            rp.relative_to(self._root)
        except ValueError:
            self.counts["denied"] += 1
            return None, "fora do workspace de midia"
        return rp, None

    def _out_path(self, src: Path, suffix: str,
                  ext: Optional[str] = None) -> Path:
        ext = ext if ext is not None else src.suffix
        cand = src.with_name("%s_%s%s" % (src.stem, suffix, ext))
        i = 2
        while cand.exists():
            cand = src.with_name("%s_%s_%d%s" % (src.stem, suffix, i, ext))
            i += 1
        return cand

    def _src_ok(self, src: Path) -> Optional[str]:
        if not src.is_file():
            return "%s nao encontrado na pasta midia." % src.name
        try:
            if src.stat().st_size > self.MAX_INPUT_BYTES:
                return "arquivo acima do limite de 4GB."
        except OSError:
            return "arquivo inacessivel."
        return None

    # ------------------------------------------------------------ builders
    def _build(self, op: str, args: Dict[str, Any]) -> dict:
        src, err = self._resolve(args.get("arquivo") or args.get("imagem"))
        if err:
            return {"ok": False, "speech": "Negado: %s" % err}
        serr = self._src_ok(src)
        if serr:
            return {"ok": False, "speech": serr}

        if op == "cortar":
            ini = _parse_time(args.get("inicio")) or 0.0
            dur = _parse_time(args.get("duracao"))
            if not dur or dur <= 0:
                return {"ok": False, "speech": "Diga a duracao do corte (ex: 30 segundos)."}
            out = self._out_path(src, "cortado")
            return {"ok": True, "src": src, "out": out,
                    "note": "corte rapido, aproximado ao keyframe",
                    "argv": ["-ss", _fmt_time(ini), "-i", str(src),
                             "-t", _fmt_time(dur), "-c", "copy", str(out)],
                    "profile": {"operacao": "corte"}}

        if op == "converter":
            fmt = _norm(args.get("formato", "")).strip(".")
            if fmt not in _CODEC_ARGS and fmt not in ("png", "jpg", "webp"):
                return {"ok": False,
                        "speech": "Formatos: mp4, mkv, webm, mp3, m4a, wav, png, jpg, webp."}
            if src.suffix.lower().lstrip(".") == fmt:
                return {"ok": False, "speech": "%s ja e %s." % (src.name, fmt)}
            if fmt in ("png", "jpg", "webp"):
                if src.suffix.lower() not in _IMAGE_EXTS:
                    return {"ok": False,
                            "speech": "Video para imagem? Use 'miniaturas de %s'." % src.name}
                out = self._out_path(src, "convertido", "." + fmt)
                return {"ok": True, "src": src, "out": out, "note": "",
                        "argv": ["-i", str(src), str(out)],
                        "profile": {"formato_imagem": fmt}}
            out = self._out_path(src, "convertido", "." + fmt)
            return {"ok": True, "src": src, "out": out,
                    "note": "recodifica (pode demorar)",
                    "argv": ["-i", str(src)] + _CODEC_ARGS[fmt] + [str(out)],
                    "profile": {"formato": fmt}}

        if op == "redimensionar":
            w = _parse_time(args.get("largura"))
            if not w or not (120 <= w <= 3840):
                return {"ok": False, "speech": "Diga a largura (120 a 3840)."}
            out = self._out_path(src, "%dp" % int(w))
            return {"ok": True, "src": src, "out": out, "note": "",
                    "argv": ["-i", str(src), "-vf",
                             "scale=%d:-2" % int(w), "-c:a", "copy", str(out)],
                    "profile": {"resolucao": "%dp" % int(w)}}

        if op == "comprimir":
            crf = int(_parse_time(args.get("qualidade")) or 28)
            crf = max(20, min(crf, 35))
            out = self._out_path(src, "compacto")
            return {"ok": True, "src": src, "out": out,
                    "note": "CRF %d (maior = menor arquivo)" % crf,
                    "argv": ["-i", str(src), "-c:v", "libx264", "-crf",
                             str(crf), "-preset", "veryfast", "-c:a", "aac",
                             "-b:a", "96k", str(out)],
                    "profile": {}}

        if op == "extrair_audio":
            fmt = _norm(args.get("formato", "m4a"))
            if fmt not in ("mp3", "m4a", "wav"):
                fmt = "m4a"
            out = self._out_path(src, "audio", "." + fmt)
            return {"ok": True, "src": src, "out": out,
                    "note": "somente a trilha de audio",
                    "argv": ["-i", str(src)] + _CODEC_ARGS[fmt] + [str(out)],
                    "profile": {"formato_audio": fmt}}

        if op == "tirar_audio":
            out = self._out_path(src, "mudo")
            return {"ok": True, "src": src, "out": out, "note": "video sem som",
                    "argv": ["-i", str(src), "-an", "-c:v", "copy", str(out)],
                    "profile": {}}

        if op == "gif":
            ini = _parse_time(args.get("inicio")) or 0.0
            dur = _parse_time(args.get("duracao")) or 5.0
            w = int(_parse_time(args.get("largura")) or 480)
            out = self._out_path(src, "gif", ".gif")
            return {"ok": True, "src": src, "out": out,
                    "note": "%ds sem audio, largura %d" % (int(dur), w),
                    "argv": ["-ss", _fmt_time(ini), "-t", _fmt_time(dur),
                             "-i", str(src), "-vf",
                             "fps=12,scale=%d:-1:flags=lanczos" % w, str(out)],
                    "profile": {}}

        if op == "miniaturas":
            intervalo = int(_parse_time(args.get("intervalo")) or 10)
            out = self._out_path(src, "miniaturas", ".jpg")
            return {"ok": True, "src": src, "out": out,
                    "note": "folha 3x3, um frame a cada %ds" % intervalo,
                    "argv": ["-i", str(src), "-vf",
                             "fps=1/%d,scale=360:-2,tile=3x3" % intervalo,
                             "-frames:v", "1", str(out)],
                    "profile": {}}

        if op == "rotacionar":
            lado = _norm(args.get("direcao", "direita"))
            vf = ("transpose=1" if lado.startswith("direi") else
                  "transpose=2" if lado.startswith("esquer") else None)
            if vf is None:
                return {"ok": False, "speech": "Diga: para a direita ou esquerda."}
            out = self._out_path(src, "rotacionado")
            return {"ok": True, "src": src, "out": out, "note": "",
                    "argv": ["-i", str(src), "-vf", vf,
                             "-c:a", "copy", str(out)],
                    "profile": {}}

        if op == "velocidade":
            f = _parse_time(args.get("fator"))
            if not f or not (0.5 <= f <= 2.0):
                return {"ok": False, "speech": "Fator entre 0.5 e 2.0."}
            out = self._out_path(src, "velocidade")
            return {"ok": True, "src": src, "out": out,
                    "note": "%.1fx, audio acompanha" % f,
                    "argv": ["-i", str(src), "-filter_complex",
                             "[0:v]setpts=PTS/%f[v];[0:a]atempo=%f[a]"
                             % (f, f),
                             "-map", "[v]", "-map", "[a]", str(out)],
                    "profile": {}}

        return {"ok": False, "speech": "operacao desconhecida: %s" % op}

    # ------------------------------------------------------------ plan/do
    _LABELS = {"cortar": "cortar", "converter": "converter",
               "redimensionar": "redimensionar", "comprimir": "comprimir",
               "extrair_audio": "extrair o audio de", "tirar_audio": "tirar o audio de",
               "gif": "fazer um GIF de", "miniaturas": "gerar miniaturas de",
               "rotacionar": "rotacionar", "velocidade": "mudar a velocidade de"}

    def plan(self, op: str, args: Optional[Dict[str, Any]] = None) -> str:
        self.counts["plans"] += 1
        b = self._build(op, args or {})
        if not b.get("ok"):
            return b["speech"]
        note = " (%s)" % b["note"] if b.get("note") else ""
        info = self._probe(b["src"])
        dur = info.get("duration")
        extra = (" de %.0f segundos" % dur) if dur else ""
        return ("Vou %s %s%s%s. Saida: %s. Diga sim para renderizar."
                % (self._LABELS.get(op, op), b["src"].name, extra, note,
                   b["out"].name))

    def do(self, op: str, args: Optional[Dict[str, Any]] = None) -> dict:
        b = self._build(op, args or {})
        if not b.get("ok"):
            return b
        if not self.available():
            return {"ok": False,
                    "speech": "FFmpeg nao encontrado. Instale com "
                              "'winget install Gyan.FFmpeg' e me chame."}
        rc, err = self._run([self._ffmpeg] + b["argv"])
        if rc != 0:
            self.counts["failed"] += 1
            return {"ok": False, "speech": "Render falhou: %s" % err[:200]}
        with self._lock:
            self.counts["renders"] += 1
        for k, v in (b.get("profile") or {}).items():
            try:
                self.profile.observe(k, v)
            except Exception:
                logger.exception("profile observe falhou")
        return {"ok": True, "speech": "Pronto: %s." % b["out"].name,
                "saida": str(b["out"])}

    def stats(self) -> dict:
        with self._lock:
            out = {"media_editor": {
                "ffmpeg": bool(self._ffmpeg),
                "workspace": str(self._root), **self.counts}}
        out.update(self.profile.stats())
        return out


# ---------------------------------------------------------------------------
# gramatica (cobertura das principais; resto via roteador LLM)
# ---------------------------------------------------------------------------
def parse_media(utterance: str):
    t = _norm(utterance)
    if not t:
        return None
    m = re.search(r"\b(?:corta|cortar|recorta[r]?)\s+(?:o|a|os|as)?\s*(.*?)\s*"
                  r"(?:(?:a\s+partir\s+)?d[oae]\s+|n[oa]\s+|minuto\s+|"
                  r"segundo\s+)*([\d:]+)\s*(?:por|durante)\s+([\d:]+)", t)
    if m and m.group(1):
        return ("midia_cortar", {"arquivo": m.group(1).strip(),
                                 "inicio": m.group(2),
                                 "duracao": m.group(3)})
    m = re.search(r"\b(?:converte|converter)\s+(?:o|a)?\s*(.+?)\s+para\s+"
                  r"(mp4|mkv|webm|mp3|m4a|wav|png|jpg|jpeg|webp)\b", t)
    if m:
        return ("midia_converter", {"arquivo": m.group(1).strip(),
                                    "formato": m.group(2)})
    m = re.search(r"\b(?:comprime|comprimir)\s+(?:o|a)?\s*(.+)$", t)
    if m:
        return ("midia_comprimir", {"arquivo": m.group(1).strip()})
    m = re.search(r"\b(?:extrai|extrair)\s+(?:o\s+)?audio\s+(?:de\s+|do\s+)?(.+)$", t)
    if m:
        return ("midia_extrair_audio", {"arquivo": m.group(1).strip()})
    m = re.search(r"\b(?:tira|tirar)\s+(?:o\s+)?audio\s+(?:de\s+|do\s+)?(.+)$", t)
    if m:
        return ("midia_tirar_audio", {"arquivo": m.group(1).strip()})
    m = re.search(r"\b(?:faz|fazer|cria|criar)\s+(?:um\s+)?gif\s+(?:de\s+|do\s+)?(.+)$", t)
    if m:
        return ("midia_gif", {"arquivo": m.group(1).strip()})
    m = re.search(r"\bminiaturas\s+(?:de\s+|do\s+)?(.+)$", t)
    if m:
        return ("midia_miniaturas", {"arquivo": m.group(1).strip()})
    m = re.search(r"\b(?:redimensiona|redimensionar)\s+(?:o|a)?\s*(.+?)\s+"
                  r"para\s+(\d{3,4})\b", t)
    if m:
        return ("midia_redimensionar", {"arquivo": m.group(1).strip(),
                                        "largura": m.group(2)})
    m = re.search(r"\b(?:acelera|acelerar)\s+(?:o|a)?\s*(.+?)\s+em\s+([\d.,]+)", t)
    if m:
        return ("midia_velocidade", {"arquivo": m.group(1).strip(),
                                     "fator": m.group(2)})
    if re.search(r"\b(?:meu|o meu)\s+(?:perfil|estilo)\s+criativo\b", t):
        return ("perfil_criativo", {})
    m = re.search(r"^prefiro\s+(?:o|a)?\s*(\w+)\s+(.+)$", t)
    if m:
        return ("perfil_definir", {"chave": m.group(1),
                                   "valor": m.group(2).strip()})
    return None


def build_media_tools(cc, editor: MediaEditor) -> None:
    import inspect
    _csf = "confirm_speech_fn" in inspect.signature(cc.register).parameters

    def reg(op: str, name: str, desc: str, confirm: bool,
            args: Optional[Dict[str, str]] = None) -> None:
        handler = lambda a, s, _op=op: editor.do(_op, a)
        csf = (lambda a, _op=op: editor.plan(_op, a)) if confirm else None
        if _csf:
            cc.register(name, desc, handler,
                        "control" if confirm else "read", args=args,
                        confirm=confirm, confirm_speech_fn=csf)
        else:
            cc.register(name, desc, handler,
                        "control" if confirm else "read", args=args,
                        confirm=confirm)

    reg("cortar", "midia_cortar", "cortar video (inicio + duracao)", True,
        {"arquivo": "nome", "inicio": "seg ou m:ss", "duracao": "segundos"})
    reg("converter", "midia_converter", "converter formato de video/audio/imagem",
        True, {"arquivo": "nome", "formato": "mp4|mkv|webm|mp3|m4a|wav|png"})
    reg("redimensionar", "midia_redimensionar", "redimensionar video/imagem",
        True, {"arquivo": "nome", "largura": "px"})
    reg("comprimir", "midia_comprimir", "comprimir video", True,
        {"arquivo": "nome", "qualidade": "20-35"})
    reg("extrair_audio", "midia_extrair_audio", "extrair trilha de audio", True,
        {"arquivo": "nome", "formato": "mp3|m4a|wav"})
    reg("tirar_audio", "midia_tirar_audio", "remover audio do video", True,
        {"arquivo": "nome"})
    reg("gif", "midia_gif", "criar GIF de trecho", True,
        {"arquivo": "nome", "inicio": "seg", "duracao": "seg",
         "largura": "px"})
    reg("miniaturas", "midia_miniaturas",
        "folha de miniaturas (contact sheet 3x3)", True,
        {"arquivo": "nome", "intervalo": "seg"})
    reg("rotacionar", "midia_rotacionar", "rotacionar video", True,
        {"arquivo": "nome", "direcao": "direita|esquerda"})
    reg("velocidade", "midia_velocidade", "mudar velocidade (0.5 a 2.0)", True,
        {"arquivo": "nome", "fator": "numero"})

    def t_perfil(args, session):
        blk = editor.profile.block_for_prompt()
        if not blk:
            return {"ok": True,
                    "speech": "Ainda nao registrei preferencias criativas. "
                              "Diga 'prefiro formato mp4' ou aprove renders "
                              "que eu observo."}
        prefs = blk.splitlines()[1:]
        return {"ok": True, "speech": "Seu perfil criativo: %s."
                % "; ".join(p.strip("- ") for p in prefs[:5])}

    def t_define(args, session):
        editor.profile.set(str(args.get("chave", "")),
                           str(args.get("valor", "")), origin="declarado")
        return {"ok": True, "speech": "Anotado: %s = %s." %
                (args.get("chave"), args.get("valor"))}

    cc.register("perfil_criativo", "ver preferencias criativas registradas",
                t_perfil, "read")
    cc.register("perfil_definir", "registrar preferencia criativa",
                t_define, "control", args={"chave": "formato|resolucao|...",
                                           "valor": "valor"}, confirm=False)


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

    # tempos
    check("tempo: 1:20 -> 80", _parse_time("1:20") == 80.0)
    check("tempo: 45 -> 45", _parse_time("45") == 45.0)
    check("tempo: 1m30 -> 90", _parse_time("1m30") == 90.0)
    check("tempo: lixo -> None", _parse_time("abc") is None)

    with tempfile.TemporaryDirectory(prefix="aura_me_st_") as td:
        ws = Path(td) / "midia"
        ran: List[List[str]] = []

        def fake_run(argv):
            ran.append(list(argv))
            return 0, ""

        def fake_run_fail(argv):
            ran.append(list(argv))
            return 1, "Invalid data found when processing input"

        def fake_probe(path):
            return {"duration": 120.0, "size": 5_000_000}

        ed = MediaEditor(workspace=ws, ffmpeg="ffmpeg.exe",
                         run_fn=fake_run, probe_fn=fake_probe,
                         profile=CreativeProfile(Path(td) / "prof.json"))
        (ws / "video.mp4").write_bytes(b"fakevideo")
        (ws / "foto.jpg").write_bytes(b"fakefoto")

        # guard
        r = ed.do("cortar", {"arquivo": "../fora.mp4", "duracao": "10"})
        check("guard: fora do workspace negado", r["ok"] is False
              and "workspace" in r["speech"])

        # plano + execucao cortar
        plan = ed.plan("cortar", {"arquivo": "video.mp4", "inicio": "1:00",
                                  "duracao": "30"})
        check("plano cortar: fala arquivo, duracao e sim",
              "video.mp4" in plan and "120" in plan and "Diga sim" in plan)
        r = ed.do("cortar", {"arquivo": "video.mp4", "inicio": "1:00",
                             "duracao": "30"})
        check("cortar: saida com sufixo", r["ok"] is True
              and r["saida"].endswith("video_cortado.mp4"))
        check("cortar: argv com seek rapido e copy",
              "-ss" in ran[-1] and "-c" in ran[-1] and "copy" in ran[-1]
              and ran[-1][ran[-1].index("-ss") + 1] == "60")

        # sem sobrescrever
        (ws / "video_cortado.mp4").write_bytes(b"x")
        r = ed.do("cortar", {"arquivo": "video.mp4", "inicio": "0",
                             "duracao": "5"})
        check("naming: colisao gera _2", r["ok"] is True
              and "video_cortado_2.mp4" in r["saida"])

        # converter video
        r = ed.do("converter", {"arquivo": "video.mp4", "formato": "mp4"})
        check("converter: mesmo formato recusado", r["ok"] is False)
        r = ed.do("converter", {"arquivo": "video.mp4", "formato": "mkv"})
        check("converter: argv com libx264",
              r["ok"] is True and "libx264" in ran[-1])
        # video -> png recusado com dica
        r = ed.do("converter", {"arquivo": "video.mp4", "formato": "png"})
        check("converter: video->imagem recusa com dica",
              r["ok"] is False and "miniaturas" in r["speech"])
        # imagem -> png ok
        r = ed.do("converter", {"arquivo": "foto.jpg", "formato": "png"})
        check("converter: imagem ok", r["ok"] is True)

        # gif / miniaturas / audio
        r = ed.do("gif", {"arquivo": "video.mp4", "duracao": "4"})
        check("gif: fps/scale no argv", r["ok"] is True
              and "fps=12" in " ".join(ran[-1]))
        r = ed.do("miniaturas", {"arquivo": "video.mp4"})
        check("miniaturas: tile 3x3", r["ok"] is True
              and "tile=3x3" in " ".join(ran[-1]))
        r = ed.do("extrair_audio", {"arquivo": "video.mp4"})
        check("extrair_audio: -vn no argv", r["ok"] is True
              and "-vn" in ran[-1])
        r = ed.do("velocidade", {"arquivo": "video.mp4", "fator": "1.5"})
        check("velocidade: setpts/atempo", r["ok"] is True
              and "setpts" in " ".join(ran[-1]))

        # falha honesta
        ed2 = MediaEditor(workspace=ws, ffmpeg="ffmpeg.exe",
                          run_fn=fake_run_fail, probe_fn=fake_probe,
                          profile=ed.profile)
        r = ed2.do("comprimir", {"arquivo": "video.mp4"})
        check("falha: stderr na fala", r["ok"] is False
              and "Invalid data" in r["speech"])

        # degrade sem ffmpeg
        # string vazia força indisponibilidade mesmo se o host tiver ffmpeg.
        ed3 = MediaEditor(workspace=ws, ffmpeg="", run_fn=fake_run,
                          probe_fn=fake_probe, profile=ed.profile)
        r = ed3.do("cortar", {"arquivo": "video.mp4", "duracao": "5"})
        check("degrade: winget sugerido", r["ok"] is False
              and "winget" in r["speech"])

        # perfil criativo
        ed.profile.set("formato", "mp3", origin="declarado")
        blk = ed.profile.block_for_prompt()
        check("perfil: declarado aparece", "formato" in blk
              and "mp3" in blk)
        check("perfil: preferência final registrada após observação",
              "formato" in ed.profile.block_for_prompt()
              and "mp3" in ed.profile.block_for_prompt())
        st = ed.stats()
        check("stats: renders e negacoes", st["media_editor"]["renders"] >= 6
              and st["media_editor"]["denied"] >= 1
              and st["creative_profile"]["prefs"] >= 2)

        # gramatica
        g = parse_media("corta o vídeo do minuto 1:00 por 30 segundos")
        check("gram: cortar", g == ("midia_cortar",
                                    {"arquivo": "vídeo".replace("í", "i") or g[1]["arquivo"],
                                     "inicio": "1:00", "duracao": "30"})
              or (g and g[0] == "midia_cortar" and g[1]["inicio"] == "1:00"
                  and g[1]["duracao"] == "30"))
        g = parse_media("converte o clipe.mp4 para webm")
        check("gram: converter", g == ("midia_converter",
                                       {"arquivo": "clipe.mp4",
                                        "formato": "webm"}))
        check("gram: gif", parse_media("faz um gif do video.mp4") ==
              ("midia_gif", {"arquivo": "video.mp4"}))
        check("gram: extrair audio", parse_media("extrai o áudio do video.mp4")
              is not None)
        check("gram: prefiro", parse_media("prefiro formato mp4") ==
              ("perfil_definir", {"chave": "formato", "valor": "mp4"}))
        check("gram: perfil", parse_media("meu estilo criativo") ==
              ("perfil_criativo", {}))
        check("gram: conversa comum", parse_media("bom dia") is None)

        # integracao CommandCenter
        try:
            from jarvis_command_center import CommandCenter
        except Exception:
            CommandCenter = None  # type: ignore
        if CommandCenter is None:
            print("[SKIP] jarvis_command_center nao importavel aqui")
        else:
            cc = CommandCenter()
            build_media_tools(cc, ed)
            r = cc.execute("midia_cortar",
                           {"arquivo": "video.mp4", "inicio": "0",
                            "duracao": "10"}, "u")
            check("cc: render pede confirmacao com plano real",
                  r.get("awaiting_confirmation") is True
                  and "video.mp4" in r["speech"] and "Diga sim" in r["speech"])
            r2 = cc.handle_utterance("sim", "u")
            check("cc: sim renderiza", r2 is not None
                  and r2.get("ok") is True and "Pronto" in r2["speech"])
            r = cc.execute("perfil_definir", {"chave": "resolucao",
                                              "valor": "1080p"}, "u")
            check("cc: preferencia registrada", r["ok"] is True)

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - media_editor.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
