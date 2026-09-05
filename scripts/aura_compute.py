#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aura_compute.py — computacao VOLUNTARIA do AURA: coordenador + no de calculo.

O QUE E (leia o CONSENT_TEXT abaixo — e o no le em voz alta antes de rodar):
    Nos consentidos da rede local doam processador OCIOSO para as simulacoes
    do AURA (grade Monte Carlo / pesquisa). Teto de uso medio configuravel,
    pausa automatica ao detectar uso da maquina, consentimento gravado em
    disco como pre-condicao FUNCIONAL (sem ele, o no se recusa a rodar),
    desinstalacao = apagar a pasta.

FRONTEIRAS DE DESENHO (deliberadas, nao limitacoes acidentais):
    - SEM tecnicas de evasao de antivirus (sem packers, ofuscacao, processo
      oculto, autostart silencioso). A forma legitima de nao ser flaggeado e
      ser visivel, assinado e consentido (ver docstring do instalador).
    - SOMENTE rede local na v1; token opcional para higiene em LAN compartilhada.
      Expor a internet exige tunel WireGuard/Tailscale + decisao a parte.
    - v1 executa CPU (registro de compute "demo" incluso; o adapter "mc_cell"
      exige o fonte do mc_grid.py na mesa e a stack nos nos — documentado).
    - Cap de GPU nao e imposto pelo no (honesto): GPU entra via workload do
      adapter futuro; no driver, limite por maquina se desejado.

PROTOCOLO (stdlib HTTP, JSON):
    POST /lease   {node_id, caps}        -> {unit|null}
    POST /result  {unit_id, metrics, digest, node_id} -> {accepted, verified}
    GET  /health                             -> estatisticas
    Unidade: {unit_id, kind, seed, params...} — deterministica por seed (§3).
    Lease com TTL: no morto -> unidade volta a pending (attempts+1).

ROTEIRO DE USO
    No PC AURA:   python scripts\\aura_compute.py --coordinator --units 200
    No no (1a vez, SEM consentimento): imprime o aviso e sai.
    No no:        python scripts\\aura_compute.py --coordinator-url http://IP_DO_AURA:8788 --aceito-termos
    Revogar:      python scripts\\aura_compute.py --revogar

INTEGRACAO FUTURA (mc_cell): builder enumera celulas (minute, lam, gap,
pressure) x horizontes com seed por celula (ja e o desenho do mc_grid, §3);
no computa via CornerSimulator e devolve metricas da celula. Exige colar o
mc_grid.py na conversa e distribuir o engine aos nos (mesmo ZIP).

stdlib only. Python 3.9+. Windows compativel. Console ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aura.compute")

__version__ = "1.0.0"

CONSENT_FILE = Path(__file__).resolve().parent / "aura_compute_consent.json"
DEFAULT_PORT = 8788
LEASE_TTL = 180.0
MAX_ATTEMPTS = 3

CONSENT_TEXT = """
=============================================================
 AURA COMPUTE NODE — AVISO DE FUNCIONAMENTO (LEIA)
=============================================================
Este programa doa poder de processamento desta maquina para as
simulacoes do projeto AURA (analise de escanteios em modo paper
trade — sem aposta, sem execucao).

COMO FUNCIONA:
- So computa com a maquina OCIOSA: sem teclado/mouse por pelo
  menos {min_idle:.0f} segundos. Ao detectar uso (jogo, ferramenta),
  pausa sozinho e retoma depois.
- Teto medio de uso: {cap:.0%} — pausa proporcional entre tarefas;
  uma thread de calculo por padrao.
- Rede: recebe unidades de calculo e devolve resultados resumidos
  (kilobytes). NAO le arquivos, navegacao, tela ou teclas. A deteccao
  de ociosidade le apenas o TEMPO desde o ultimo input — nunca o
  conteudo dele.
- Nada sai da rede local configurada.

COMO PAUSAR AGORA: Ctrl+C (ou feche a janela).
COMO SAIR DE VEZ: rode com --revogar (remove o consentimento).
COMO DESINSTALAR: apague a pasta. Sem registro do Windows, sem
  servico oculto, sem inicializacao automatica que voce nao marcou.

Este no roda SOMENTE com consentimento explicito gravado em disco.
Sem consentimento, ele se recusa a executar. Se voce nao e o dono
desta maquina e nao viu este aviso antes da instalacao, nao aceite.
=============================================================
"""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# registro de computacao — deterministico por seed (requisito §3)
# ---------------------------------------------------------------------------
def compute_demo(unit: dict) -> dict:
    """Workload de demonstracao/teste: soma de aleatorios com seed fixa.
    random.Random(seed) e estavel entre plataformas/versoes do CPython —
    pre-requisito para a verificacao do coordenador bater."""
    rng = random.Random(int(unit["seed"]))
    n = int(unit.get("n", 10000))
    s = 0.0
    for _ in range(n):
        s += rng.random()
    return {"mean": s / n, "n": n}


COMPUTE: Dict[str, Callable[[dict], dict]] = {"demo": compute_demo}
# "mc_cell": PONTO DE INTEGRACAO — adapter do mc_grid.py (CornerSimulator,
# seed por celula). Exige o fonte na mesa; nao inventado aqui.


def digest_of(metrics: dict) -> str:
    return hashlib.sha256(json.dumps(metrics, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def build_demo_units(count: int, seed_base: int = 1000, n: int = 50000) -> List[dict]:
    return [{"unit_id": "demo/%06d" % i, "kind": "demo",
             "seed": seed_base + i, "n": n} for i in range(count)]


# ---------------------------------------------------------------------------
# consentimento — pre-condicao FUNCIONAL do no
# ---------------------------------------------------------------------------
def consent_state(path: Optional[Path] = None) -> Optional[dict]:
    p = Path(path) if path else CONSENT_FILE
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_consent(cap: float, min_idle: float, path: Optional[Path] = None) -> dict:
    p = Path(path) if path else CONSENT_FILE
    rec = {"accepted_at": _iso_now(), "cap": float(cap),
           "min_idle": float(min_idle), "host": socket.gethostname()}
    p.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def revoke_consent(path: Optional[Path] = None) -> bool:
    p = Path(path) if path else CONSENT_FILE
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False


def require_consent(cap: float, min_idle: float, path: Optional[Path] = None) -> dict:
    st = consent_state(path)
    if st is None:
        print(CONSENT_TEXT.format(cap=cap, min_idle=min_idle))
        print("Para aceitar: python %s --coordinator-url http://IP:PORTA --aceito-termos"
              % Path(sys.argv[0]).name)
        raise SystemExit(2)
    return st


# ---------------------------------------------------------------------------
# deteccao de ociosidade (Windows, ctypes/stdlib) — so o TEMPO, nunca conteudo
# ---------------------------------------------------------------------------
def _windows_idle_seconds() -> Optional[float]:
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        now = ctypes.windll.kernel32.GetTickCount()
        return ((now - lii.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


def _default_idle_seconds() -> Optional[float]:
    if os.name == "nt":
        return _windows_idle_seconds()
    return None  # sem deteccao nativa: assume ocioso (honesto; log avisa)


# ---------------------------------------------------------------------------
# coordenador
# ---------------------------------------------------------------------------
class UnitStore:
    """Fila de unidades com lease/TTL, verificacao por reamostragem e
    quarentena de unidades problematicas. Thread-safe; compute fora do lock."""

    def __init__(self, units: List[dict], compute_registry: Dict[str, Callable],
                 verify_prob: float = 0.25, lease_ttl: float = LEASE_TTL):
        self._lock = threading.Lock()
        self._units = {u["unit_id"]: dict(u) for u in units}
        self._state: Dict[str, str] = {uid: "pending" for uid in self._units}
        self._lease: Dict[str, Dict[str, Any]] = {}
        self._attempts: Dict[str, int] = {uid: 0 for uid in self._units}
        self._results: Dict[str, dict] = {}
        self._compute = compute_registry
        self.verify_prob = float(verify_prob)
        self.lease_ttl = float(lease_ttl)
        self.stats = {"leased": 0, "completed": 0, "rejected": 0,
                      "expired_requeues": 0, "quarantined": 0,
                      "verifications": 0, "verif_failed": 0,
                      "nodes": {}}

    # ------------------------------------------------------------ internos
    def _sweep_expired_locked(self, now: float) -> None:
        for uid, st in self._state.items():
            if st != "leased":
                continue
            lz = self._lease.get(uid)
            if lz and now - lz["ts"] > self.lease_ttl:
                self._state[uid] = "pending"
                self._attempts[uid] += 1
                self.stats["expired_requeues"] += 1

    # ------------------------------------------------------------ api
    def lease(self, node_id: str, now: Optional[float] = None) -> Optional[dict]:
        now = time.time() if now is None else now
        with self._lock:
            self._sweep_expired_locked(now)
            for uid in sorted(self._units):
                if self._state[uid] != "pending":
                    continue
                self._state[uid] = "leased"
                self._lease[uid] = {"node": node_id, "ts": now}
                self.stats["leased"] += 1
                self.stats["nodes"][node_id] = now
                return dict(self._units[uid])
            return None

    def complete(self, unit_id: str, metrics: dict, digest: str, node_id: str,
                 now: Optional[float] = None) -> dict:
        now = time.time() if now is None else now
        with self._lock:
            self._sweep_expired_locked(now)
            if self._state.get(unit_id) != "leased":
                return {"accepted": False, "reason": "not_leased_or_unknown"}
            lz = self._lease.get(unit_id)
            if lz and lz["node"] != node_id:
                return {"accepted": False, "reason": "lease_owner_mismatch"}
            unit = self._units[unit_id]

        # verificacao FORA do lock (compute demora)
        verified: Optional[bool] = None
        if random.random() < self.verify_prob:
            fn = self._compute.get(unit.get("kind"))
            if fn is None:
                return {"accepted": False, "reason": "unknown_kind_coordinator"}
            try:
                expected = digest_of(fn(unit))
                verified = (expected == digest)
                self.stats["verifications"] += 1
                if not verified:
                    self.stats["verif_failed"] += 1
            except Exception:
                logger.exception("verify falhou para %s", unit_id)
                verified = False

        digest_selfconsistent = (digest == digest_of(metrics))
        ok = digest_selfconsistent and (verified is not False)
        with self._lock:
            if ok:
                self._state[unit_id] = "done"
                self._results[unit_id] = {"metrics": metrics, "digest": digest,
                                          "node": node_id, "ts": now,
                                          "verified": verified}
                self.stats["completed"] += 1
                return {"accepted": True, "verified": verified}
            self.stats["rejected"] += 1
            self._attempts[unit_id] += 1
            if self._attempts[unit_id] >= MAX_ATTEMPTS:
                self._state[unit_id] = "quarantined"
                self.stats["quarantined"] += 1
            else:
                self._state[unit_id] = "pending"
            reason = ("digest_mismatch" if not digest_selfconsistent
                      else "verification_failed")
            return {"accepted": False, "verified": verified, "reason": reason}

    def summary(self) -> dict:
        with self._lock:
            counts: Dict[str, int] = {}
            for st in self._state.values():
                counts[st] = counts.get(st, 0) + 1
            return {"units": dict(counts), "stats": dict(self.stats),
                    "results": dict(self._results)}

    def pending_available(self) -> bool:
        with self._lock:
            return any(s == "pending" for s in self._state.values())


class _CoordinatorHandler(BaseHTTPRequestHandler):
    server: "ComputeCoordinatorServer"

    def log_message(self, fmt: str, *args: Any) -> None:  # logs via logger
        logger.debug("%s %s", self.address_string(), fmt % args)

    def _reply(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        if not self.server.token:
            return True
        return self.headers.get("X-AURA-Token") == self.server.token

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._reply(404, {"ok": False, "error": "rota desconhecida"})
            return
        s = self.server.store.summary()
        self._reply(200, {"ok": True, "service": "aura_compute_coordinator",
                          "version": __version__, **s})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reply(401, {"ok": False, "error": "token invalido"})
            return
        body = self._read_body()
        if self.path == "/lease":
            unit = self.server.store.lease(str(body.get("node_id", "?")))
            self._reply(200, {"ok": True, "unit": unit})
            return
        if self.path == "/result":
            resp = self.server.store.complete(
                str(body.get("unit_id", "")), body.get("metrics") or {},
                str(body.get("digest", "")), str(body.get("node_id", "?")))
            if resp.get("accepted") and self.server.journal:
                try:
                    with open(self.server.journal, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({
                            "unit_id": body.get("unit_id"),
                            "metrics": body.get("metrics"),
                            "digest": body.get("digest"),
                            "node": body.get("node_id"),
                            "verified": resp.get("verified"),
                            "ts": _iso_now()}, ensure_ascii=False) + "\n")
                except OSError:
                    logger.exception("journal falhou")
            self._reply(200, {"ok": True, **resp})
            return
        self._reply(404, {"ok": False, "error": "rota desconhecida"})


class ComputeCoordinatorServer(ThreadingHTTPServer):
    def __init__(self, addr, store: UnitStore, token: Optional[str],
                 journal: Optional[str]):
        super().__init__(addr, _CoordinatorHandler)
        self.store = store
        self.token = token
        self.journal = journal
        self.daemon_threads = True


class ComputeCoordinator:
    def __init__(self, units: List[dict],
                 compute_registry: Optional[Dict[str, Callable]] = None,
                 verify_prob: float = 0.25, token: Optional[str] = None,
                 journal_path: Optional[str] = None):
        self.store = UnitStore(units, compute_registry or COMPUTE, verify_prob)
        self.token = token
        self.journal = journal_path
        self._httpd: Optional[ComputeCoordinatorServer] = None

    def serve_background(self, host: str = "127.0.0.1", port: int = 0
                         ) -> ComputeCoordinatorServer:
        self._httpd = ComputeCoordinatorServer((host, port), self.store,
                                                self.token, self.journal)
        threading.Thread(target=self._httpd.serve_forever, daemon=True,
                         name="aura-compute-coord").start()
        return self._httpd


# ---------------------------------------------------------------------------
# no de computacao
# ---------------------------------------------------------------------------
class ComputeNode:
    def __init__(self, coordinator_url: str, node_id: Optional[str] = None,
                 cap: float = 0.5, min_idle: float = 300.0,
                 poll_interval: float = 5.0, pause_sleep: float = 30.0,
                 token: Optional[str] = None, idle_fn: Optional[Callable] = None,
                 compute_registry: Optional[Dict[str, Callable]] = None):
        self.url = coordinator_url.rstrip("/")
        self.node_id = node_id or ("%s-%d" % (socket.gethostname(), os.getpid()))
        self.cap = min(max(float(cap), 0.05), 1.0)
        self.min_idle = float(min_idle)
        self.poll = float(poll_interval)
        self.pause_sleep = float(pause_sleep)
        self.token = token
        self.idle_fn = idle_fn if idle_fn is not None else _default_idle_seconds
        self.compute = compute_registry or COMPUTE
        self.stats = {"units_done": 0, "units_failed": 0, "compute_s": 0.0,
                      "idle_pauses": 0, "posts_failed": 0}
        self._last_compute_s = 0.0

    def _post(self, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-AURA-Token"] = self.token
        req = urllib.request.Request(self.url + path,
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _is_idle(self) -> bool:
        s = self.idle_fn()
        if s is None:
            return True  # sem deteccao nativa — assume ocioso (log acima)
        return s >= self.min_idle

    def _compute_unit(self, unit: dict) -> dict:
        fn = self.compute.get(unit.get("kind"))
        if fn is None:
            raise ValueError("kind desconhecido no no: %r" % unit.get("kind"))
        return fn(unit)

    def run(self, max_units: Optional[int] = None, exit_when_empty: bool = False,
            max_wall_s: Optional[float] = None) -> str:
        """Loop principal. Retorna motivo da parada. Consentimento e exigido
        no main() (ponto de entrada) — aqui e protocolo puro."""
        t0 = time.monotonic()
        done = 0
        while max_units is None or done < max_units:
            if max_wall_s is not None and time.monotonic() - t0 > max_wall_s:
                return "wall_limit"
            if not self._is_idle():
                self.stats["idle_pauses"] += 1
                time.sleep(self.pause_sleep)
                continue
            try:
                resp = self._post("/lease", {"node_id": self.node_id,
                                             "caps": {"cap": self.cap,
                                                      "min_idle": self.min_idle}})
            except Exception as exc:
                self.stats["posts_failed"] += 1
                logger.warning("lease falhou (%s); tentando de novo", exc)
                time.sleep(self.poll * 2)
                continue
            unit = resp.get("unit")
            if not unit:
                if exit_when_empty:
                    return "empty"
                time.sleep(self.poll)
                continue
            t1 = time.monotonic()
            try:
                metrics = self._compute_unit(unit)
            except Exception:
                logger.exception("compute falhou para %s", unit.get("unit_id"))
                self.stats["units_failed"] += 1
                time.sleep(self.poll)
                continue
            self._last_compute_s = time.monotonic() - t1
            self.stats["compute_s"] += self._last_compute_s
            self.stats["units_done"] += 1

            done += 1
            try:
                self._post("/result", {"unit_id": unit["unit_id"],
                                       "metrics": metrics,
                                       "digest": digest_of(metrics),
                                       "node_id": self.node_id})
            except Exception as exc:
                self.stats["posts_failed"] += 1
                logger.warning("post de resultado falhou (%s); lease expira e "
                               "a unidade volta a fila", exc)
            # duty-cycle: pausa proporcional ao tempo de compute (teto medio)
            compute_s = self._last_compute_s
            sleep_s = compute_s * (1.0 / self.cap - 1.0)
            if sleep_s > 0:
                time.sleep(min(sleep_s, 60.0))
        return "max_units"


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="aura_compute.py",
                                 description="AURA — computacao voluntaria "
                                             "(coordenador / no consentido)")
    ap.add_argument("--coordinator", action="store_true",
                    help="roda como coordenador no PC do AURA")
    ap.add_argument("--units", type=int, default=100,
                    help="quantidade de unidades demo (coordinator)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--token", default=None,
                    help="token compartilhado (higiene em LAN compartilhada)")
    ap.add_argument("--journal", default=None,
                    help="jsonl de resultados aceitos (coordinator)")
    ap.add_argument("--coordinator-url", default=None,
                    help="URL do coordenador (modo no)")
    ap.add_argument("--cap", type=float, default=0.5,
                    help="teto medio de uso (0.5 = 50%%)")
    ap.add_argument("--min-idle", type=float, default=300.0,
                    help="segundos de ociosidade exigidos antes de computar")
    ap.add_argument("--aceito-termos", action="store_true",
                    help="GRAVA consentimento apos ler o aviso")
    ap.add_argument("--revogar", action="store_true",
                    help="remove o consentimento e sai")
    ap.add_argument("--max-units", type=int, default=None)
    ap.add_argument("--exit-when-empty", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.revogar:
        revoke_consent()
        print("Consentimento removido. O no se recusa a rodar ate novo aceite.")
        return 0

    if args.coordinator:
        units = build_demo_units(args.units)
        # mc_cell: substituir pelo builder real quando mc_grid.py estiver na mesa
        coord = ComputeCoordinator(units, token=args.token,
                                   journal_path=args.journal)
        httpd = coord.serve_background(args.host, args.port)
        print("Coordenador AURA em http://%s:%d — %d unidades, "
              "verificacao por reamostragem ativa." %
              (args.host, httpd.server_address[1], len(units)))
        if args.token:
            print("Token exigido dos nos (X-AURA-Token).")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("Coordenador encerrado.")
        return 0

    if args.coordinator_url:
        if args.aceito_termos:
            rec = write_consent(args.cap, args.min_idle)
            print("Consentimento gravado: %s" % json.dumps(rec))
        require_consent(args.cap, args.min_idle)
        if os.name != "nt":
            print("[aviso] deteccao de ociosidade nativa so no Windows; "
                  "assumindo maquina sempre ociosa — use --min-idle 0 se "
                  "souber o que faz.")
        node = ComputeNode(args.coordinator_url, cap=args.cap,
                           min_idle=args.min_idle, token=args.token)
        print("No %s -> %s (cap %.0f%%, ocioso >= %.0fs). Ctrl+C pausa."
              % (node.node_id, node.coordinator_url if hasattr(node, "coordinator_url")
                 else args.coordinator_url, args.cap * 100, args.min_idle))
        try:
            reason = node.run(max_units=args.max_units,
                              exit_when_empty=args.exit_when_empty)
            print("Parado: %s — %s" % (reason, json.dumps(node.stats)))
        except KeyboardInterrupt:
            print("Pausado pelo usuario. %s" % json.dumps(node.stats))
        return 0

    ap.print_help()
    return 2


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory(prefix="aura_compute_st_") as td:
        cpath = Path(td) / "consent.json"

        # 1) gate de consentimento
        try:
            require_consent(0.5, 300, path=cpath)
            blocked = False
        except SystemExit:
            blocked = True
        check("gate: sem consentimento o no se recusa (SystemExit)", blocked)
        rec = write_consent(0.5, 300, path=cpath)
        check("gate: aceite gravado com dados",
              consent_state(path=cpath) == rec)
        check("gate: revogacao apaga", revoke_consent(path=cpath) is True
              and consent_state(path=cpath) is None)

        # 2) determinismo do workload (base da verificacao)
        u = build_demo_units(1, n=20000)[0]
        d1, d2 = digest_of(compute_demo(u)), digest_of(compute_demo(u))
        check("workload deterministico por seed", d1 == d2)

        # 3) loop completo coordenador<->no (verificacao sempre ligada)
        journal = str(Path(td) / "results.jsonl")
        units = build_demo_units(5, n=20000)
        coord = ComputeCoordinator(units, verify_prob=1.0, journal_path=journal)
        httpd = coord.serve_background("127.0.0.1", 0)
        port = httpd.server_address[1]
        url = "http://127.0.0.1:%d" % port
        node = ComputeNode(url, node_id="t1", cap=1.0, poll_interval=0.02,
                           pause_sleep=0.02, idle_fn=lambda: 9999.0)
        reason = node.run(max_units=5)
        check("loop: no completa 5 unidades", reason == "max_units"
              and node.stats["units_done"] == 5)
        s = coord.store.summary()
        check("loop: coordenador marca tudo done",
              s["units"].get("done") == 5 and s["stats"]["completed"] == 5)
        check("loop: verificacao executada nas 5",
              s["stats"]["verifications"] >= 5 and s["stats"]["verif_failed"] == 0)
        with open(journal, encoding="utf-8") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()]
        check("journal: 5 resultados gravados", len(lines) == 5)
        httpd.shutdown()

        # 4) tamper: resultado errado com digest auto-consistente e rejeitado
        units2 = build_demo_units(3, seed_base=7000, n=20000)
        coord2 = ComputeCoordinator(units2, verify_prob=1.0)
        store = coord2.store
        lu = store.lease("evil", now=100.0)
        fake = {"mean": 0.123456, "n": lu["n"]}
        resp = store.complete(lu["unit_id"], fake, digest_of(fake), "evil",
                              now=100.5)
        check("tamper: resultado falso rejeitado",
              resp["accepted"] is False and resp["verified"] is False)
        check("tamper: unidade volta a pending",
              store.summary()["units"].get("pending") == 3)

        # 5) lease expira e reenfileira (no morto nao perde unidade)
        lu2 = store.lease("slow", now=200.0)
        store.complete(lu2["unit_id"], {"x": 1}, digest_of({"x": 1}), "slow",
                       now=200.0 + LEASE_TTL + 10)
        check("lease TTL: expirado reenfileirado",
              store.summary()["stats"]["expired_requeues"] >= 1)

        # 6) pausa por uso da maquina (jogo/ferramenta detectada)
        coord3 = ComputeCoordinator(build_demo_units(3, n=100))
        httpd3 = coord3.serve_background("127.0.0.1", 0)
        busy = ComputeNode("http://127.0.0.1:%d" % httpd3.server_address[1],
                           node_id="busy", cap=1.0, poll_interval=0.02,
                           pause_sleep=0.05, idle_fn=lambda: 0.0)
        r = busy.run(max_units=1, max_wall_s=0.4)
        check("idle: maquina em uso -> no pausa sem computar",
              r == "wall_limit" and busy.stats["units_done"] == 0
              and busy.stats["idle_pauses"] >= 3)
        httpd3.shutdown()

        # 7) duty-cycle: cap 50% -> wall >= ~2x compute
        coord4 = ComputeCoordinator(build_demo_units(2, n=300000))
        httpd4 = coord4.serve_background("127.0.0.1", 0)
        duty = ComputeNode("http://127.0.0.1:%d" % httpd4.server_address[1],
                           node_id="duty", cap=0.5, poll_interval=0.02,
                           pause_sleep=0.02, idle_fn=lambda: 9999.0)
        t0 = time.monotonic()
        duty.run(max_units=2)
        wall = time.monotonic() - t0
        comp = duty.stats["compute_s"]
        check("duty-cycle: cap 50%% respeitado (wall>=1.7x compute)",
              comp > 0 and wall >= comp * 1.7,
              "wall=%.2fs compute=%.2fs" % (wall, comp))
        httpd4.shutdown()

        # 8) token: no sem token nao conversa com coordenador com token
        coord5 = ComputeCoordinator(build_demo_units(2, n=100), token="s3cr3t")
        httpd5 = coord5.serve_background("127.0.0.1", 0)
        intruder = ComputeNode("http://127.0.0.1:%d" % httpd5.server_address[1],
                               node_id="intruder", cap=1.0, poll_interval=0.02,
                               pause_sleep=0.02, idle_fn=lambda: 9999.0)
        intruder.run(max_wall_s=0.3)
        check("token: no sem token e recusado (posts_failed>0, 0 unidades)",
              intruder.stats["posts_failed"] > 0
              and intruder.stats["units_done"] == 0)
        okn = ComputeNode("http://127.0.0.1:%d" % httpd5.server_address[1],
                          node_id="ok", cap=1.0, poll_interval=0.02,
                          pause_sleep=0.02, idle_fn=lambda: 9999.0,
                          token="s3cr3t")
        okn.run(max_units=2)
        check("token: no com token completa", okn.stats["units_done"] == 2)
        httpd5.shutdown()

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - aura_compute.py")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
