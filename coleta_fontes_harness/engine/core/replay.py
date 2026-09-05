#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA QUANT-X V25 — Replay deterministico sobre os journals JSONL.

Local: engine/core/replay.py
Dependencias: NENHUMA (stdlib). Python 3.9+. Windows OK.

O que habilita:
  1. A/B de modelos: champion vs challenger sobre os MESMOS frames,
     com digest SHA-256 provando que o input foi o mesmo.
  2. Post-mortem: "o que o sistema viu exatamente as 87:12?" via
     extract_segment(fixture, minuto).
  3. Validacao de upgrade: rodar o pipeline novo sobre o historico
     gravado ANTES de promove-lo ao ar.

Regras de determinismo:
  - Tempo NUNCA vem do relogio de parede: vem do registro (received_at /
    view.raw_ts) via ReplayClock injetado no contexto.
  - patch_time(clock) torna legado time.time()-dependente deterministico
    (global ao processo — use apenas em processo dedicado de replay).
  - Digest de outputs: SHA-256 sobre serializacao canonica. Duas runs
    sobre o mesmo stream com o mesmo digest = pipeline reprodutivel.

Tolerancia de leitura:
  - ultima linha truncada (crash na escrita) -> skip, logada.
  - linha invalida no meio -> skip e logada (strict=True levanta).
  - .jsonl e .jsonl.gz; arquivos .tmp ignorados; ordenacao por data no nome.

Invariante: modulo somente-leitura sobre os journals.
"""
from __future__ import annotations

import contextlib
import gzip
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

log = logging.getLogger("aura.replay")

__version__ = "1.0.0"
__all__ = [
    "RecordMeta", "iter_records", "scan_replay_files", "ReplayClock",
    "ReplayContext", "ReplayRunner", "RunResult", "ABReport", "run_ab",
    "extract_segment", "stream_digest", "patch_time", "record_timestamp",
]

_DATE_RE = re.compile(r"(\d{8})")


# ---------------------------------------------------------------------------
# Varredura de arquivos
# ---------------------------------------------------------------------------
def _file_sort_key(p: Path) -> tuple:
    m = _DATE_RE.search(p.name)
    if m:
        return (0, m.group(1), p.name)
    try:
        mt = f"{p.stat().st_mtime:.0f}"
    except OSError:
        mt = "0"
    return (1, mt, p.name)


def scan_replay_files(root, *, recursive: bool = False) -> List[Path]:
    """Retorna journals JSONL ordenados (datados por data no nome, resto por mtime).

    Aceita *.jsonl e *.jsonl.gz. Ignora .tmp e dotfiles.
    """
    root = Path(root)
    if root.is_file():
        return [root]
    it = root.rglob("*.jsonl*") if recursive else root.glob("*.jsonl*")
    out: List[Path] = []
    for p in it:
        if not p.is_file():
            continue
        if p.name.endswith(".tmp") or p.name.startswith("."):
            continue
        if not (p.name.endswith(".jsonl") or p.name.endswith(".jsonl.gz")):
            continue
        out.append(p)
    return sorted(out, key=_file_sort_key)


# ---------------------------------------------------------------------------
# Leitura tolerante
# ---------------------------------------------------------------------------
@dataclass
class RecordMeta:
    file: str
    line: int
    seq: int


def _open_text(p: Path):
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    return open(p, "r", encoding="utf-8", errors="replace")


def iter_records(paths, *, strict: bool = False,
                 on_error: Optional[Callable[[str, str, int, str], None]] = None
                 ) -> Iterator[Tuple[RecordMeta, dict]]:
    """Itera registros JSONL de varios arquivos, em ordem.

    on_error(kind, path, line_no, msg) recebe 'partial_line', 'bad_line',
    'open_failed'. strict=True transforma bad_line/open_failed em excecao.
    """
    def _notify(kind: str, path: Path, line_no: int, msg: str) -> None:
        if on_error is not None:
            try:
                on_error(kind, str(path), line_no, msg)
            except Exception:
                log.exception("[replay] callback on_error falhou")
        log.warning("[replay] %s %s:%d — %s", kind, path, line_no, msg)

    def _emit(raw: str, line_no: int, path: Path, seq: int):
        s = raw.strip()
        if not s:
            return
        try:
            rec = json.loads(s)
        except ValueError as e:
            if strict:
                raise ValueError(f"{path}:{line_no}: json invalido: {e}") from e
            _notify("bad_line", path, line_no, f"json invalido: {e}")
            return
        if not isinstance(rec, dict):
            _notify("bad_line", path, line_no, "registro nao-dict")
            return
        yield RecordMeta(str(path), line_no, seq), rec

    seq = 0
    for path in paths:
        path = Path(path)
        try:
            fh = _open_text(path)
        except OSError as e:
            if strict:
                raise
            _notify("open_failed", path, 0, str(e))
            continue
        with fh:
            pending: Optional[str] = None
            pending_no = 0
            line_no = 0
            for raw in fh:
                line_no += 1
                if pending is not None:
                    seq += 1
                    yield from _emit(pending, pending_no, path, seq)
                pending, pending_no = raw, line_no
            if pending is not None:
                if pending.endswith("\n") or not pending.strip():
                    seq += 1
                    yield from _emit(pending, pending_no, path, seq)
                else:
                    # ultima linha sem newline: so aceita se for JSON completo
                    try:
                        rec = json.loads(pending.strip())
                    except ValueError:
                        _notify("partial_line", path, pending_no,
                                "ultima linha sem newline e invalida (truncada?)")
                        continue
                    if isinstance(rec, dict):
                        seq += 1
                        yield RecordMeta(str(path), pending_no, seq), rec
                    else:
                        _notify("bad_line", path, pending_no, "registro nao-dict")


# ---------------------------------------------------------------------------
# Tempo deterministico
# ---------------------------------------------------------------------------
def _parse_iso(s: Any) -> Optional[float]:
    if not isinstance(s, str) or not s.strip():
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _parse_any_ts(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        if f > 1e12:
            f /= 1000.0  # epoch em ms
        return f if f > 0 else None
    return _parse_iso(v)


def record_timestamp(record: dict) -> Optional[float]:
    """Epoch do registro: received_at > view.raw_ts > ts."""
    f = _parse_iso(record.get("received_at"))
    if f is not None:
        return f
    v = record.get("view") if isinstance(record.get("view"), dict) else {}
    f = _parse_any_ts(v.get("raw_ts"))
    if f is not None:
        return f
    return _parse_any_ts(record.get("ts"))


class ReplayClock:
    """Tempo derivado do registro em processamento (nunca do relogio de parede)."""

    def __init__(self, *, start: float = 0.0, step: float = 1.0):
        self._ts = start
        self._mono = 0.0
        self._step = step

    def advance(self, record: dict, frame_index: int) -> None:
        ts = record_timestamp(record)
        self._ts = ts if ts is not None else self._ts + self._step
        self._mono = float(frame_index)

    def time(self) -> float:
        return self._ts

    def monotonic(self) -> float:
        return self._mono

    def sleep(self, seconds: float) -> None:
        self._mono += max(0.0, float(seconds))  # NUNCA dorme de verdade


@contextlib.contextmanager
def patch_time(clock: ReplayClock, *, patch_datetime: bool = False):
    """Substitui time.time/monotonic/sleep (e opcionalmente datetime.now).

    CUIDADO: e GLOBAL ao processo. Use apenas em processo/thread dedicado de
    replay, sempre dentro do with. Restaura os originais na saida.
    """
    saved_time, saved_mono, saved_sleep = time.time, time.monotonic, time.sleep
    saved_dt_now = datetime.now
    time.time = clock.time  # type: ignore[assignment]
    time.monotonic = clock.monotonic  # type: ignore[assignment]
    time.sleep = clock.sleep  # type: ignore[assignment]
    if patch_datetime:
        def _now(tz=None):
            dt = datetime.fromtimestamp(clock.time(), tz=timezone.utc)
            return dt if tz is None else dt.astimezone(tz)
        datetime.now = _now  # type: ignore[assignment]
    try:
        yield
    finally:
        time.time, time.monotonic, time.sleep = saved_time, saved_mono, saved_sleep
        if patch_datetime:
            datetime.now = saved_dt_now  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
@dataclass
class ReplayContext:
    index: int
    record: dict
    meta: RecordMeta
    clock: ReplayClock

    @property
    def view(self) -> dict:
        v = self.record.get("view")
        return v if isinstance(v, dict) else {}

    @property
    def payload(self) -> dict:
        p = self.record.get("payload")
        return p if isinstance(p, dict) else {}


@dataclass
class RunResult:
    outputs: List[Any]
    errors: List[dict]
    stats: dict
    digest: str


def _digest_outputs(outputs: List[Any]) -> str:
    h = hashlib.sha256()
    for o in outputs:
        try:
            h.update(json.dumps(o, sort_keys=True, default=str).encode("utf-8"))
        except Exception:
            h.update(repr(o).encode("utf-8"))
    return h.hexdigest()[:16]


class ReplayRunner:
    """Roda fn(ctx) sobre cada frame do stream. Erro por frame nao mata a run."""

    def __init__(self, paths: Optional[Sequence[Any]] = None, *,
                 records: Optional[List[dict]] = None,
                 use_patched_time: bool = False):
        if paths is None and records is None:
            raise ValueError("informe paths ou records")
        self.paths = [Path(p) for p in paths] if paths else None
        self._records = records
        self.use_patched_time = use_patched_time

    def _iter(self):
        if self._records is not None:
            for i, rec in enumerate(self._records):
                yield RecordMeta("memory", 0, i), rec
        else:
            yield from iter_records(self.paths or [])

    def run(self, fn: Callable[[ReplayContext], Any]) -> RunResult:
        clock = ReplayClock()
        outputs: List[Any] = []
        errors: List[dict] = []
        t0 = time.perf_counter()
        idx = 0
        cm = patch_time(clock) if self.use_patched_time else contextlib.nullcontext()
        with cm:
            for meta, rec in self._iter():
                clock.advance(rec, idx)
                ctx = ReplayContext(index=idx, record=rec, meta=meta, clock=clock)
                try:
                    outputs.append(fn(ctx))
                except Exception as e:
                    errors.append({"index": idx, "file": meta.file,
                                   "line": meta.line,
                                   "error": f"{type(e).__name__}: {e}"})
                idx += 1
        return RunResult(outputs=outputs, errors=errors,
                         stats={"frames": idx, "errors": len(errors),
                                "elapsed_sec": round(time.perf_counter() - t0, 3)},
                         digest=_digest_outputs(outputs))


# ---------------------------------------------------------------------------
# A/B: champion vs challenger
# ---------------------------------------------------------------------------
def _canon(x: Any, nd: int = 9) -> Any:
    if isinstance(x, float):
        return round(x, nd)
    if isinstance(x, dict):
        return {k: _canon(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_canon(v, nd) for v in x]
    return x


def _trunc(x: Any, n: int = 200) -> str:
    s = repr(x)
    return s if len(s) <= n else s[:n] + "..."


@dataclass
class ABReport:
    n_frames: int
    n_equal: int
    n_diff: int
    errors_a: int
    errors_b: int
    digest_a: str
    digest_b: str
    diffs: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"n_frames": self.n_frames, "n_equal": self.n_equal,
                "n_diff": self.n_diff, "errors_a": self.errors_a,
                "errors_b": self.errors_b, "digest_a": self.digest_a,
                "digest_b": self.digest_b, "diffs": self.diffs}

    def summary(self) -> str:
        lines = [
            f"A/B: {self.n_frames} frames | iguais={self.n_equal} "
            f"divergentes={self.n_diff} (erros a={self.errors_a}, b={self.errors_b})",
            f"digest champion={self.digest_a} challenger={self.digest_b}"
            + ("  [IDENTICOS]" if self.digest_a == self.digest_b else ""),
        ]
        for d in self.diffs[:10]:
            lines.append(f"  frame #{d['index']}: A={d['champion']} | B={d['challenger']}")
        return "\n".join(lines)


def run_ab(paths, champion: Callable[[ReplayContext], Any],
           challenger: Callable[[ReplayContext], Any], *,
           max_report: int = 20, tolerance_nd: int = 9) -> ABReport:
    """Roda dois pipelines sobre os MESMOS frames e relata divergencias.

    Compare com tolerancia de float (round nd casas). Divergencia = decisao
    diferente entre versoes no mesmo frame — o sinal de que o upgrade muda
    comportamento onde (e somente onde) se espera.
    """
    runner = ReplayRunner(paths=paths)
    ra = runner.run(champion)
    rb = runner.run(challenger)
    n = min(len(ra.outputs), len(rb.outputs))
    diffs: List[dict] = []
    n_diff = 0
    for i in range(n):
        a = _canon(ra.outputs[i], tolerance_nd)
        b = _canon(rb.outputs[i], tolerance_nd)
        if a != b:
            n_diff += 1
            if len(diffs) < max_report:
                diffs.append({"index": i, "champion": _trunc(a),
                              "challenger": _trunc(b)})
    return ABReport(n_frames=n, n_equal=n - n_diff, n_diff=n_diff,
                    errors_a=len(ra.errors), errors_b=len(rb.errors),
                    digest_a=ra.digest, digest_b=rb.digest, diffs=diffs)


# ---------------------------------------------------------------------------
# Post-mortem e auditabilidade
# ---------------------------------------------------------------------------
def extract_segment(paths, *, fixture: Optional[str] = None,
                    minute_from: Optional[float] = None,
                    minute_to: Optional[float] = None,
                    limit: Optional[int] = None) -> List[dict]:
    """Frames crus (payload + view) de uma fixture/janela — post-mortem exato."""
    out: List[dict] = []
    for _meta, rec in iter_records(paths):
        v = rec.get("view") if isinstance(rec.get("view"), dict) else {}
        if fixture is not None:
            fid = v.get("fixture_id")
            if fid is None and v.get("home") and v.get("away"):
                fid = f"{v.get('home')}x{v.get('away')}"
            if str(fid) != str(fixture):
                continue
        m = None
        try:
            if v.get("minute") is not None:
                m = float(v.get("minute"))
        except (TypeError, ValueError):
            m = None
        if minute_from is not None and (m is None or m < minute_from):
            continue
        if minute_to is not None and (m is None or m > minute_to):
            continue
        out.append(rec)
        if limit is not None and len(out) >= limit:
            break
    return out


def stream_digest(paths, *, fields: Optional[Sequence[str]] = None) -> str:
    """SHA-256 do conteudo do stream (prova de input identico entre A/Bs)."""
    h = hashlib.sha256()
    for _meta, rec in iter_records(paths):
        if fields:
            rec = {k: rec.get(k) for k in fields}
        h.update(json.dumps(rec, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Self-test: python engine/core/replay.py
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    failures: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {extra}" if extra else ""))
        if not cond:
            failures.append(name)

    def env(fid: str, m: int) -> dict:
        # received_at usa segundos do dia (m * 60) — ISO valido; minute do jogo fica em view
        sec = int(m) * 60
        hh, mm, ss = sec // 3600, (sec % 3600) // 60, sec % 60
        return {"received_at": f"2026-08-23T{hh:02d}:{mm:02d}:{ss:02d}+00:00",
                "fingerprint": f"{fid}|m{m}",
                "view": {"fixture_id": fid, "minute": m,
                         "corners_home": 1, "corners_away": 2},
                "payload": {"fixture": {"id": fid, "minute": m}}}

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        f1 = td / "live_feed-20260823.jsonl"
        f1.write_text("\n".join(json.dumps(env("F1", m)) for m in (80, 82, 84)) + "\n",
                      encoding="utf-8")
        f2 = td / "live_feed-20260824.jsonl"
        f2.write_text("\n".join(json.dumps(env("F2", m)) for m in (30, 38, 46)) + "\n",
                      encoding="utf-8")
        f3 = td / "probe.jsonl.gz"
        import gzip as _gz
        with _gz.open(f3, "wt", encoding="utf-8") as f:
            f.write(json.dumps(env("F3", 10)) + "\n" + json.dumps(env("F3", 12)) + "\n")
        f4 = td / "partial.jsonl"
        f4.write_text(json.dumps(env("F4", 50)) + "\n" + json.dumps(env("F4", 52)) + "\n"
                      + '{"view": {"minute": 9', encoding="utf-8")  # truncado
        paths = scan_replay_files(td)

        # T1: contagem com tolerancia a linha truncada
        recs = list(iter_records(paths))
        check("iter_records: 10 registros validos, truncada descartada",
              len(recs) == 10, f"{len(recs)}")

        # T2: determinismo do runner (digest estavel entre runs)
        def fn(ctx: ReplayContext):
            return {"m": ctx.view.get("minute"), "t": ctx.clock.time()}

        runner = ReplayRunner(paths=paths)
        r1 = runner.run(fn)
        time.sleep(0.03)  # wall-clock avanca; digest nao pode mudar
        r2 = runner.run(fn)
        check("digest identico entre runs (relógio do registro)",
              r1.digest == r2.digest and r1.stats["errors"] == 0)
        check("saida usa received_at como tempo",
              r1.outputs[0]["t"] > 1.6e9 and abs(r1.outputs[0]["t"] - r2.outputs[0]["t"]) < 1e-9,
              f"t={r1.outputs[0]['t']}")

        # T3: patch_time torna time.time() legado deterministico
        def legacy_fn(ctx: ReplayContext):
            return {"wall": time.time()}  # codigo legado intocado

        rp = ReplayRunner(paths=paths, use_patched_time=True)
        p1 = rp.run(legacy_fn)
        time.sleep(0.02)
        p2 = rp.run(legacy_fn)
        check("patch_time: time.time() deterministico sob replay",
              p1.digest == p2.digest and p1.outputs[0]["wall"] > 1.6e9)
        check("patch_time: originais restaurados", time.time() > 1.6e9)

        # T4: A/B detecta divergencia exata
        def champ(ctx: ReplayContext):
            return ctx.view.get("minute")

        def chall(ctx: ReplayContext):
            return ctx.view.get("minute") + (1 if ctx.index == 5 else 0)

        rep = run_ab(paths, champ, chall)
        check("A/B: 1 divergencia no frame 5",
              rep.n_diff == 1 and rep.diffs and rep.diffs[0]["index"] == 5,
              rep.summary().splitlines()[0])
        rep_same = run_ab(paths, champ, champ)
        check("A/B: pipelines iguais -> zero divergencia",
              rep_same.n_diff == 0 and rep_same.digest_a == rep_same.digest_b)

        # T5: extract_segment (post-mortem)
        seg = extract_segment(paths, fixture="F2", minute_from=30, minute_to=40)
        check("extract_segment: F2 30-40' = 2 frames",
              len(seg) == 2 and all("payload" in s for s in seg))

        # T6: stream_digest estavel e sensivel a mudanca
        d1, d2 = stream_digest(paths), stream_digest(paths)
        check("stream_digest deterministico", d1 == d2)
        with f4.open("a", encoding="utf-8") as f:
            # newline separa o lixo truncado do novo registro valido
            f.write("\n" + json.dumps(env("F4", 54)) + "\n")
        check("stream_digest muda quando o stream muda",
              stream_digest(paths) != d1)

    print(f"\nreplay selftest: {len(failures)} falha(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
