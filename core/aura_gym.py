#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA GYM v1.0 — academia de falhas do Maestro.
Treina em SIMULAÇÃO (SimSystem). Nunca toca no sistema vivo.
Gera cenários, injeta fault, o Maestro (catalog.diagnose) decide,
o Juiz verifica, tudo vira experiência no ledger + playbooks.
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ══ 1. CÓPIA MENTAL ══════════════════════════════════════════


class SimService:
    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.state = "up"  # up | down | occupied | slow | half_boot | flapping
        self.restarts = 0


class SimSystem:
    """Réplica lógica: portas, dependências (cascata), recursos."""

    DEPENDS = {
        "bridge": [],
        "engine": ["ollama"],
        "matriz": ["engine"],
        "voice": ["ollama"],
        "hermes": ["ollama"],
    }

    def __init__(self):
        self.services = {
            n: SimService(n, p)
            for n, p in {
                "bridge": 8080,
                "engine": 8765,
                "matriz": 8766,
                "voice": 8099,
                "hermes": 8777,
            }.items()
        }
        self.ollama_up = True
        self.ram = 62.0
        self.log_mb = 120.0

    def inject(self, fault: "Fault") -> "SimSystem":
        s = self.services.get(fault.service)
        mode = fault.mode
        params = fault.params or {}

        if mode == "port_closed" and s:
            s.state = "down"
        elif mode == "port_occupied" and s:
            s.state = "occupied"
        elif mode == "slow_response" and s:
            s.state = "slow"
        elif mode == "flapping" and s:
            s.state = "flapping"
        elif mode == "resource_starved":
            self.ram = float(params.get("ram", 93.0))
        elif mode == "log_flood":
            self.log_mb = float(params.get("mb", 2500.0))
        elif mode == "dependency_down" and fault.service == "ollama":
            self.ollama_up = False
        elif mode == "cascading_down":
            for name in params.get("services", []):
                if name in self.services:
                    self.services[name].state = "down"

        # Efeito cascata: dependência caída → dependente half_boot
        for name, deps in self.DEPENDS.items():
            if self.services[name].state == "up":
                for d in deps:
                    if (d == "ollama" and not self.ollama_up) or (
                        d in self.services and self.services[d].state == "down"
                    ):
                        self.services[name].state = "half_boot"
        return self

    def observe(self) -> dict:
        """Evidência no MESMO formato aproximado que o sistema real produz."""
        ports = {
            n: ("OK" if s.state in ("up", "slow") else "OFF")
            for n, s in self.services.items()
        }
        ports["ollama"] = "OK" if self.ollama_up else "OFF"
        lines = [
            "AURA paper-trade | exec bloqueada. "
            + " ".join(f"{k.title()} {v}" for k, v in ports.items())
        ]
        for n, s in self.services.items():
            if s.state == "down":
                lines.append(f"log: {n} exited with code 1")
            if s.state == "occupied":
                lines.append(f"log: {n} winerror 10048 address already in use")
            if s.state == "flapping":
                lines.append(f"log: {n} restart loop detected")
            if s.state == "half_boot":
                lines.append(f"log: {n} up but health check failing")
        if self.ram > 85:
            lines.append(f'snapshot: mem_percent": {self.ram:.1f}')
        if self.log_mb > 800:
            lines.append(f"log dir size {self.log_mb:.0f}MB")
        return {
            "port_status": "\n".join(lines),
            "snapshot": f'cpu 12.3 mem_percent": {self.ram:.1f}',
        }

    def apply(self, action: Tuple[str, Optional[str]]) -> "SimSystem":
        kind, target = action
        if kind == "restart_service" and target in self.services:
            s = self.services[target]
            if s.state in ("down", "occupied", "flapping", "half_boot"):
                s.state = "up"
                s.restarts += 1
        elif kind == "fix_common":
            for s in self.services.values():
                if s.state in ("down", "occupied", "flapping"):
                    s.state = "up"
                    s.restarts += 1
        elif kind == "reduce_memory":
            self.ram = min(self.ram, 78.0)
        elif kind == "rotate_logs":
            self.log_mb = 50.0

        # half_boot recupera quando dependência volta
        for name, deps in self.DEPENDS.items():
            if self.services[name].state == "half_boot":
                ok_deps = True
                for d in deps:
                    if d == "ollama" and not self.ollama_up:
                        ok_deps = False
                    elif d in self.services and self.services[d].state not in (
                        "up",
                        "slow",
                    ):
                        ok_deps = False
                if ok_deps:
                    self.services[name].state = "up"
        return self

    def healthy(self, target: Optional[str] = None) -> bool:
        if target == "ollama":
            return self.ollama_up
        if target and target in self.services:
            return self.services[target].state in ("up", "slow")
        return self.ollama_up and all(
            s.state in ("up", "slow") for s in self.services.values()
        )


# ══ 2. GERADOR (taxonomia → milhares) ════════════════════════


@dataclass
class Fault:
    service: str
    mode: str
    context: str
    params: Dict[str, Any] = field(default_factory=dict)

    def id(self) -> str:
        return f"{self.service}:{self.mode}:{self.context}"


SERVICES = ["bridge", "engine", "matriz", "voice", "ollama"]
MODES = [
    "port_closed",
    "port_occupied",
    "slow_response",
    "resource_starved",
    "log_flood",
    "dependency_down",
    "flapping",
]
CONTEXTS = ["idle", "live_game", "high_load", "post_boot"]

ACTION_MAP = {
    "E-NET-003": ("restart_service", "bridge"),
    "E-NET-004": ("restart_service", "engine"),
    "E-NET-005": ("restart_service", "matriz"),
    "E-NET-006": ("fix_common", None),
    "E-SYS-001": ("reduce_memory", None),
}


def generate_scenarios(max_n: int = 5000, seed: int = 42) -> List[List[Fault]]:
    rng = random.Random(seed)
    out: List[List[Fault]] = []

    # Nível 1 — simples
    for s, m, c in product(SERVICES, MODES, CONTEXTS):
        p: Dict[str, Any] = {}
        if m == "resource_starved":
            p = {"ram": round(rng.uniform(88, 97), 1)}
        if m == "log_flood":
            p = {"mb": round(rng.uniform(800, 3000))}
        # dependency_down só faz sentido para ollama
        if m == "dependency_down" and s != "ollama":
            continue
        out.append([Fault(s, m, c, p)])

    # Nível 2 — compostas (pares)
    simples = [
        f
        for fl in out
        for f in fl
        if f.mode in ("port_closed", "port_occupied", "slow_response", "flapping")
    ]
    for a, b in product(simples, simples):
        if a.service < b.service:
            out.append([a, b])
            if len(out) >= max_n:
                return out[:max_n]

    # Nível 3 — triplas aleatórias até max_n
    while len(out) < max_n and len(simples) >= 3:
        out.append(rng.sample(simples, 3))
    return out[:max_n]


# ══ 3. TREINO + LEDGER ══════════════════════════════════════


class GymTrainer:
    def __init__(
        self,
        catalog=None,
        ledger: str = r"C:\aura\logs_supervisor\gym_ledger.jsonl",
        root: str = r"C:\aura",
    ):
        self.catalog = catalog
        self.root = Path(root)
        self.ledger = Path(ledger)
        if not self.ledger.is_absolute():
            self.ledger = self.root / "logs_supervisor" / "gym_ledger.jsonl"
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.stats = {
            "trained": 0,
            "solved": 0,
            "new_patterns": 0,
            "no_policy": 0,
            "failed": 0,
        }

    def _ensure_catalog(self):
        if self.catalog is not None:
            return self.catalog
        try:
            # tenta import relativo ao pacote
            sys.path.insert(0, str(self.root))
            sys.path.insert(0, str(self.root / "core"))
            from aura_error_catalog import ErrorCatalog  # type: ignore

            self.catalog = ErrorCatalog(root=str(self.root))
            return self.catalog
        except Exception:
            try:
                from core.aura_error_catalog import ErrorCatalog  # type: ignore

                self.catalog = ErrorCatalog(root=str(self.root))
                return self.catalog
            except Exception as e:
                raise RuntimeError(f"ErrorCatalog indisponivel: {e}") from e

    def run_session(self, n: int = 500, seed: int = 7) -> str:
        catalog = self._ensure_catalog()
        scenarios = generate_scenarios(max_n=max(n, 500))
        random.Random(seed).shuffle(scenarios)

        for faults in scenarios[:n]:
            sim = SimSystem()
            for f in faults:
                sim.inject(f)
            target = faults[0].service
            evidence = sim.observe()

            try:
                diag = catalog.diagnose(evidence)
            except Exception as e:
                diag = {"known": False, "code": None, "error": str(e)}

            if not isinstance(diag, dict):
                diag = {"known": False}

            action = None
            if diag.get("known") and diag.get("code"):
                action = ACTION_MAP.get(str(diag["code"]))

            if action is None:
                if not diag.get("known"):
                    self.stats["new_patterns"] += 1
                else:
                    self.stats["no_policy"] += 1
                self._record(faults, None, diag.get("code"), None)
                continue

            sim.apply(action)
            solved = sim.healthy(target if target != "ollama" else None)
            # resource_starved / log_flood: veredito por recurso
            if faults[0].mode == "resource_starved":
                solved = sim.ram <= 80
            if faults[0].mode == "log_flood":
                solved = sim.log_mb < 200

            self.stats["trained"] += 1
            if solved:
                self.stats["solved"] += 1
            else:
                self.stats["failed"] += 1
            self._record(faults, action, diag.get("code"), solved)

        return self.report()

    def _record(self, faults, action, code, solved):
        rec = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "scenario": [f.id() for f in faults],
            "action": str(action) if action else None,
            "code": code,
            "solved": solved,
        }
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def report(self) -> str:
        s = self.stats
        rate = s["solved"] / max(1, s["trained"])
        return (
            f"GYM SESSION — {s['trained']} treinados · "
            f"{s['solved']} resolvidos ({rate:.0%}) · "
            f"{s['failed']} falharam · "
            f"{s['new_patterns']} padroes NOVOS p/ catalogar · "
            f"{s['no_policy']} sem politica · "
            f"ledger={self.ledger}"
        )


# ══ 4. DISTILLER — ledger → playbooks ════════════════════════


def distill_playbooks(
    ledger: str = r"C:\aura\logs_supervisor\gym_ledger.jsonl",
    min_trials: int = 3,
    min_rate: float = 0.9,
) -> Dict[str, str]:
    """Extrai assinatura→ação com ≥90% de sucesso. Ganho de XP mensurável."""
    path = Path(ledger)
    if not path.exists():
        return {}
    stats: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])  # wins, trials
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        if rec.get("solved") is None or not rec.get("action"):
            continue
        for sid in rec.get("scenario") or []:
            sig = ":".join(str(sid).split(":")[:2])  # service:mode
            key = (sig, str(rec["action"]))
            stats[key][1] += 1
            stats[key][0] += int(bool(rec["solved"]))
    return {
        f"{sig} → {act}": f"{w}/{t} ({w / t:.0%})"
        for (sig, act), (w, t) in stats.items()
        if t >= min_trials and (w / t) >= min_rate
    }


def export_alpaca_dataset(
    ledger: str = r"C:\aura\logs_supervisor\gym_ledger.jsonl",
    out: str = r"C:\aura\logs_supervisor\gym_alpaca_dataset.jsonl",
) -> int:
    """Exporta pares (evidência → diagnóstico/ação) no formato Alpaca para fine-tune."""
    path = Path(ledger)
    if not path.exists():
        return 0
    n = 0
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fout:
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            if not rec.get("code"):
                continue
            instruction = (
                "Voce e o Hermes, copiloto LOCAL do AURA QUANT-X (paper-trade). "
                "Dado o cenario de falha, diga o codigo E-XXX e a acao correta. "
                "Nunca invente. execution_allowed=false."
            )
            inp = f"Cenario: {rec.get('scenario')}"
            out_text = (
                f"Codigo: {rec.get('code')}. Acao: {rec.get('action')}. "
                f"Resolvido: {rec.get('solved')}."
            )
            fout.write(
                json.dumps(
                    {
                        "instruction": instruction,
                        "input": inp,
                        "output": out_text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n += 1
    return n


# ══ CLI ══════════════════════════════════════════════════════


def main():
    import argparse

    p = argparse.ArgumentParser(description="AURA GYM — treino offline do Maestro")
    p.add_argument("n", nargs="?", type=int, default=500, help="cenarios a treinar")
    p.add_argument("--root", default=r"C:\aura")
    p.add_argument("--ledger", default=None)
    p.add_argument("--distill", action="store_true", help="so destilar playbooks")
    p.add_argument("--export-alpaca", action="store_true")
    args = p.parse_args()

    root = Path(args.root)
    ledger = args.ledger or str(root / "logs_supervisor" / "gym_ledger.jsonl")

    if args.distill:
        pb = distill_playbooks(ledger)
        print(f"Playbooks provados: {len(pb)}")
        for k, v in list(pb.items())[:20]:
            print(f"  {k}  {v}")
        return

    if args.export_alpaca:
        n = export_alpaca_dataset(ledger)
        print(f"Exportados {n} exemplos Alpaca → gym_alpaca_dataset.jsonl")
        return

    trainer = GymTrainer(catalog=None, ledger=ledger, root=str(root))
    print(trainer.run_session(n=args.n))
    pb = distill_playbooks(ledger)
    print(f"Playbooks >=90%: {len(pb)}")
    for k, v in list(pb.items())[:10]:
        print(f"  {k}  {v}")


if __name__ == "__main__":
    main()
