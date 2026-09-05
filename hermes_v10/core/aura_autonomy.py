#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autonomy Engine v2.0 â€” o maestro (medico + bombeiro + faxineiro).
Loop: RCA -> detecta -> decide (politica) -> executa -> VERIFICA -> avisa -> aprende
+ preditivo slope/ETA + hot-reload catalogo + janitor + post-mortem + toast
+ modo manutencao + heartbeat.

Regra de ouro: deterministico sempre; LLM nunca decide autonomia.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("aura.autonomy")

DEPS: Dict[str, List[str]] = {
    "bridge": [],
    "engine": ["ollama"],
    "matriz": ["engine"],
    "voice": ["ollama"],
    "hermes": ["ollama"],
}

AUTO_FIX_POLICY: Dict[str, int] = {
    "E-NET-003": 180,
    "E-NET-004": 180,
    "E-NET-005": 300,
    "E-NET-006": 300,
    "E-CODE-001": 120,
    "E-CODE-002": 120,
    "E-CODE-003": 120,
    "E-SYS-001": 180,
    "E-SYS-002": 180,
    "E-FE-001": 120,
    "E-BE-001": 120,
}

MAX_FIXES_PER_HOUR = 6
VERIFY_WAIT_S = 45
CYCLE_S = 60

CODE_BY_SERVICE = {
    "bridge": "E-NET-003",
    "engine": "E-NET-004",
    "matriz": "E-NET-005",
}


class AutonomyEngine:
    def __init__(
        self,
        catalog=None,
        alerts=None,
        agents=None,
        memory=None,
        root: str = r"C:\aura",
        load_agents: Optional[Callable] = None,
    ):
        self.catalog = catalog
        self.alerts = alerts
        self.agents = agents
        self.memory = memory
        self.load_agents = load_agents
        self.root = Path(root)
        self.last_fix: Dict[str, float] = {}
        self.history: List[Tuple[float, str, bool]] = []
        self.enabled = threading.Event()
        self.enabled.set()
        self.maintenance = threading.Event()
        self.maintenance.clear()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._catalog_mtime = 0.0
        self._mem_hist: deque = deque(maxlen=30)
        self._disk_hist: deque = deque(maxlen=60)
        self._last_janitor: Dict[str, float] = {}
        self.last_beat = time.time()

    def _agents(self):
        if self.agents is not None:
            return self.agents
        if self.load_agents:
            try:
                self.agents = self.load_agents()
            except Exception as e:
                logger.warning("autonomy_agents_load_fail %s", e)
        return self.agents

    def _evidence(self) -> Dict[str, Any]:
        ev: Dict[str, Any] = {"snapshot": self._snapshot()}
        try:
            ag = self._agents()
            if ag is not None:
                ev["port_status"] = (
                    ag.status_text() if hasattr(ag, "status_text") else str(ag)
                )
        except Exception as e:
            ev["port_status"] = f"agents_unavailable: {e}"
        return ev

    def _snapshot(self) -> Dict[str, Any]:
        try:
            import psutil
            return {
                "cpu": psutil.cpu_percent(0.05),
                "mem": psutil.virtual_memory().percent,
            }
        except Exception:
            return {}

    def _can_fix(self, code: str) -> Tuple[bool, str]:
        if code not in AUTO_FIX_POLICY:
            return False, "politica expandida â€” so alerta"
        now = time.time()
        if now - self.last_fix.get(code, 0) < AUTO_FIX_POLICY[code]:
            return False, "cooldown ativo"
        hour_count = len([1 for t, _, _ in self.history if now - t < 3600])
        if hour_count >= MAX_FIXES_PER_HOUR:
            return False, "CIRCUIT BREAKER (muitos fixes na ultima hora) â€” humano necessario"
        return True, ""

    def _verify(self, code: str) -> bool:
        urls = {
            "E-NET-003": "http://127.0.0.1:8080/health",
            "E-NET-004": "http://127.0.0.1:8765/api/health",
            "E-NET-005": "http://127.0.0.1:8766/health",
        }
        url = urls.get(code)
        if url:
            try:
                from urllib.request import Request, urlopen
                with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=3) as r:
                    if 200 <= getattr(r, "status", 0) < 300:
                        return True
            except Exception:
                pass
        try:
            ag = self._agents()
            if ag is None or not hasattr(ag, "status_text"):
                return False
            status = ag.status_text()
            port_ok = {
                "E-NET-003": "Bridge OK",
                "E-NET-004": "Engine OK",
                "E-NET-005": "Matriz OK",
            }.get(code)
            if port_ok:
                return port_ok in status
            return ("Engine OK" in status) or ("Bridge OK" in status)
        except Exception:
            return False

    def _off_services(self) -> Tuple[Set[str], bool]:
        try:
            ag = self._agents()
            if ag is None:
                return set(), True
            if hasattr(ag, "full_status"):
                fs = ag.full_status()
                ports = fs.get("ports") or {}
                off = {k for k, v in ports.items() if str(v).upper() in ("OFF", "DOWN", "0")}
                ollama_ok = str(ports.get("ollama", "OK")).upper() in ("OK", "UP", "200")
                return off, ollama_ok
            st = ag.status_text() if hasattr(ag, "status_text") else ""
            off: Set[str] = set()
            for name in DEPS:
                if f"{name.title()} OFF" in st or f"{name} OFF" in st:
                    off.add(name)
            ollama_ok = True
            if "Ollama OFF" in st or "ollama OFF" in st:
                ollama_ok = False
            return off, ollama_ok
        except Exception:
            return set(), True

    def analyze_root_causes(self, down: Set[str], ollama_ok: bool) -> dict:
        if not ollama_ok:
            sintomas = [s for s in down if "ollama" in DEPS.get(s, [])]
            return {
                "roots": [],
                "cause": "ollama",
                "symptoms": sintomas,
                "action": "alert_human",
                "note": "Ollama (intocavel) e a CAUSA. Reiniciar sintomas = quebrar restarts a toa.",
            }
        roots = [
            s for s in down
            if not any(d in down or (d == "ollama" and not ollama_ok) for d in DEPS.get(s, []))
        ]
        return {
            "roots": roots,
            "cause": None,
            "symptoms": sorted(down - set(roots)),
            "action": "fix_roots",
            "note": f"Fixar raizes {roots}; {sorted(down - set(roots))} recuperam em cascata.",
        }

    def _maybe_reload_catalog(self) -> None:
        if not self.catalog:
            return
        try:
            path = getattr(self.catalog, "catalog_path", None)
            if path is None:
                path = self.root / "core" / "aura_error_catalog.json"
            path = Path(path)
            if not path.exists():
                return
            m = path.stat().st_mtime
            if m > self._catalog_mtime:
                if hasattr(self.catalog, "load"):
                    self.catalog.load()
                self._catalog_mtime = m
                n = len(getattr(self.catalog, "entries", {}) or {})
                self._alert("info", "SYSTEM", f"Catalogo recarregado - {n} entradas ativas sem restart")
        except Exception:
            pass

    def _slope(self, ys: List[float]) -> float:
        n = len(ys)
        if n < 10:
            return 0.0
        mx = (n - 1) / 2.0
        my = sum(ys) / n
        num = sum((i - mx) * (y - my) for i, y in enumerate(ys))
        den = sum((i - mx) ** 2 for i in range(n))
        return num / den if den else 0.0

    def _predictive_v2(self) -> None:
        snap = self._snapshot()
        mem = snap.get("mem")
        if isinstance(mem, (int, float)):
            self._mem_hist.append(float(mem))
            slope = self._slope(list(self._mem_hist))
            if mem >= 90:
                self._toast("AURA Â· RAM CRITICA", f"RAM {mem:.0f}% â€” agir agora")
                self._alert("critical", "E-SYS-001", f"RAM {mem:.0f}% critico")
            elif slope > 0.3 and mem > 72:
                eta = (90 - mem) / slope if slope else 999
                self._alert("warning", "PRED",
                    f"RAM {mem:.0f}% subindo {slope:.1f}%/ciclo â†’ 90% em ~{eta:.0f} min")
        try:
            root_str = str(self.root)
            drive = root_str[:3] if len(root_str) >= 3 and root_str[1] == ":" else "/"
            usage = shutil.disk_usage(drive)
            free_gb = usage.free / 1e9
            log_dir = self.root / "logs_supervisor"
            log_mb = 0.0
            if log_dir.exists():
                log_mb = sum(f.stat().st_size for f in log_dir.glob("*.log") if f.is_file()) / 1e6
            self._disk_hist.append((log_mb, free_gb))
            growth = self._slope([m for m, _ in self._disk_hist])
            if growth > 0.5 and free_gb < 20:
                eta_h = (free_gb * 1024 / growth / 60) if growth else 999
                self._alert("warning", "PRED",
                    f"Disco: logs +{growth:.0f}MB/ciclo, {free_gb:.0f}GB livres â†’ cheio em ~{eta_h:.0f}h")
            elif free_gb < 5:
                self._toast("AURA Â· DISCO CRITICO", f"{free_gb:.1f}GB livres")
                self._alert("critical", "E-SYS-DISK", f"Disco critico: {free_gb:.1f}GB livres")
        except Exception:
            pass

    def _toast(self, title: str, msg: str) -> None:
        try:
            from plyer import notification
            notification.notify(title=title, message=msg[:200], timeout=8)
            return
        except Exception:
            pass
        try:
            safe_title = title.replace("'", "")
            safe_msg = msg[:150].replace("'", "")
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 f"[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                 f"[System.Windows.Forms.MessageBox]::Show('{safe_msg}','{safe_title}',0,64)"],
                creationflags=0x08000000,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _postmortem(self, code: str, reason: str) -> None:
        pm = self.root / "logs_supervisor" / "postmortems"
        pm.mkdir(parents=True, exist_ok=True)
        fp = pm / f"PM_{code}_{datetime.now():%Y%m%d_%H%M}.md"
        timeline = "\n".join(
            f"- {datetime.fromtimestamp(t).strftime('%H:%M:%S')} Â· {c} Â· "
            f"{'OK' if ok else 'FALHOU'}"
            for t, c, ok in self.history[-15:]
        )
        try:
            ag = self._agents()
            evid = ag.status_text() if ag and hasattr(ag, "status_text") else "(status indisponivel)"
        except Exception:
            evid = "(status indisponivel)"
        try:
            fp.write_text(
                f"# POST-MORTEM {code} â€” {datetime.now():%Y-%m-%d %H:%M}\n\n"
                f"## Motivo\n{reason}\n\n## Estado na hora\n{evid}\n\n"
                f"## Acoes autonomas recentes\n{timeline or '(nenhuma)'}\n\n"
                f"## Proximo passo\n"
                f"- Fix falhou 2x â†’ provavel causa fora do catalogo â†’ triage\n"
                f"- Reproduzir no gym: `python core/aura_gym.py 200`\n",
                encoding="utf-8",
            )
            self._toast(f"AURA Â· {code}", "Fix falhou â€” post-mortem salvo")
        except Exception as e:
            logger.warning("postmortem_write_fail %s", e)

    def _janitor(self) -> None:
        JOBS = {
            "prune_memory": 7 * 86400,
            "rotate_logs": 6 * 3600,
            "backup_catalog": 86400,
        }
        now = time.time()
        for job, interval in JOBS.items():
            if now - self._last_janitor.get(job, 0) < interval:
                continue
            self._last_janitor[job] = now
            try:
                if job == "prune_memory" and self.memory and hasattr(self.memory, "prune_old"):
                    self.memory.prune_old(days=30)
                    logger.info("janitor_prune_memory_ok")
                elif job == "rotate_logs":
                    log_dir = self.root / "logs_supervisor"
                    if log_dir.exists():
                        for f in log_dir.glob("*.log"):
                            try:
                                if f.stat().st_size > 20_000_000:
                                    f.rename(f.with_suffix(f".{int(now)}.rotated"))
                            except Exception:
                                pass
                elif job == "backup_catalog" and self.catalog:
                    bdir = self.root / "logs_supervisor" / "catalog_backups"
                    bdir.mkdir(parents=True, exist_ok=True)
                    src = Path(
                        getattr(self.catalog, "catalog_path", None)
                        or (self.root / "core" / "aura_error_catalog.json")
                    )
                    if src.exists():
                        (bdir / f"catalog_{datetime.now():%Y%m%d}.json").write_text(
                            src.read_text(encoding="utf-8"), encoding="utf-8"
                        )
            except Exception as e:
                logger.warning("janitor_%s_failed %s", job, e)

    def _alert(self, sev: str, code: str, msg: str) -> None:
        try:
            if self.alerts is not None:
                if hasattr(self.alerts, "send"):
                    try:
                        result = self.alerts.send(sev, f"autonomy:{code}", msg, {})
                        # Coroutine detectada em contexto síncrono → fecha para não gerar RuntimeWarning
                        if hasattr(result, "close"):
                            result.close()
                    except Exception:
                        pass
                elif hasattr(self.alerts, "emit"):
                    self.alerts.emit(sev, f"autonomy:{code}", msg)
        except Exception:
            pass
        try:
            logdir = self.root / "logs_supervisor"
            logdir.mkdir(parents=True, exist_ok=True)
            line = f"{datetime.utcnow().isoformat()}Z\t{sev}\t{code}\t{msg}\n"
            with (logdir / "autonomy.jsonl").open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
        logger.warning("autonomy %s %s %s", sev, code, msg)

    def _cycle(self) -> None:
        if not self.enabled.is_set() or not self.catalog:
            return
        self.last_beat = time.time()
        self._maybe_reload_catalog()
        self._janitor()
        self._predictive_v2()

        off, ollama_ok = self._off_services()
        if off or not ollama_ok:
            rca = self.analyze_root_causes(off, ollama_ok)
            if rca["action"] == "alert_human":
                self._toast("AURA Â· OLLAMA OFF", "Causa-raiz detectada â€” intervencao humana")
                self._alert("critical", "E-NET-002",
                    f"RCA: Ollama e a causa de {rca['symptoms']}. NAO reiniciar sintomas.")
                return
            for root_svc in rca.get("roots") or []:
                code = CODE_BY_SERVICE.get(root_svc)
                if not code:
                    continue
                if self.maintenance.is_set():
                    self._alert("info", code, f"Modo manutencao: radar detectou {code}, fix SUSPENSO")
                    continue
                ok, why = self._can_fix(code)
                if not ok:
                    self._alert("info", code, f"Auto-fix suspenso ({why})")
                    continue
                with self._lock:
                    self.last_fix[code] = time.time()
                try:
                    result = self.catalog.apply_fix(code)
                except Exception as e:
                    result = f"apply_fix_error: {e}"
                self._alert("info", code, f"Auto-fix (raiz): {result}")
                time.sleep(VERIFY_WAIT_S)
                sucesso = self._verify(code)
                with self._lock:
                    self.history.append((time.time(), code, bool(sucesso)))
                if sucesso:
                    self._alert("info", code,
                        f"OK {code} RESOLVIDO â€” cascata deve recuperar {rca.get('symptoms')}")
                else:
                    recent_fails = [1 for t, c, s in self.history
                                    if c == code and not s and time.time() - t < 86400]
                    if len(recent_fails) >= 2:
                        self._postmortem(code, "Fix falhou 2x em 24h â€” breaker implicito")
                    self._alert("critical", code,
                        f"FALHA {code} auto-fix apos verificacao. Intervencao humana.")
            return

        try:
            diag = self.catalog.diagnose(self._evidence())
        except Exception as e:
            logger.warning("autonomy_diagnose_fail %s", e)
            return
        if not isinstance(diag, dict) or not diag.get("known"):
            return
        code = str(diag.get("code") or "")
        title = str(diag.get("title") or "")
        if not code:
            return
        self._alert("warning", code, f"Deteccao autonoma: {code} Â· {title}")
        if self.maintenance.is_set():
            self._alert("info", code, f"Modo manutencao: detectou {code}, fix SUSPENSO")
            return
        ok, why = self._can_fix(code)
        if not ok:
            self._alert("info", code, f"Auto-fix NAO executado ({why})")
            return
        with self._lock:
            self.last_fix[code] = time.time()
        try:
            result = self.catalog.apply_fix(code)
        except Exception as e:
            result = f"apply_fix_error: {e}"
        self._alert("info", code, f"Auto-fix EXECUTANDO: {result}")
        time.sleep(VERIFY_WAIT_S)
        sucesso = self._verify(code)
        with self._lock:
            self.history.append((time.time(), code, bool(sucesso)))
        if sucesso:
            self._alert("info", code, f"OK {code} RESOLVIDO autonomamente. Sistema estavel.")
        else:
            recent_fails = [1 for t, c, s in self.history
                            if c == code and not s and time.time() - t < 86400]
            if len(recent_fails) >= 2:
                self._postmortem(code, "Fix falhou 2x em 24h")
            self._alert("critical", code,
                f"FALHA {code} auto-fix apos verificacao. Intervencao humana.")
        try:
            if self.memory and hasattr(self.memory, "store"):
                from core.hermes_memory_engine import MemoryEntry  # type: ignore
                self.memory.store(MemoryEntry(
                    id=f"auto_{code}_{int(time.time())}",
                    ts=datetime.utcnow().isoformat() + "Z",
                    role="system",
                    content=f"autonomy {code} success={sucesso} result={str(result)[:200]}",
                    source="autonomy",
                    tags=["autonomy", code, "ok" if sucesso else "fail"],
                ))
        except Exception:
            pass

    def toggle(self, on: bool) -> str:
        if on:
            self.enabled.set()
        else:
            self.enabled.clear()
        return (f"Autonomia {'LIGADA' if on else 'DESLIGADA'}. "
                f"Historico: {len(self.history)} acoes. "
                f"Manutencao: {'ON' if self.maintenance.is_set() else 'OFF'}.")

    def set_maintenance(self, on: bool) -> str:
        if on:
            self.maintenance.set()
        else:
            self.maintenance.clear()
        return (f"Modo manutencao {'ATIVADO' if on else 'DESATIVADO'}. "
                f"Radar continua; auto-fix {'SUSPENSO' if on else 'permitido pela politica'}.")

    def report(self) -> str:
        alive = (time.time() - self.last_beat) < (CYCLE_S * 3)
        if not self.history:
            return (f"Nenhuma acao autonoma ainda. Radar a cada {CYCLE_S}s. "
                    f"Politica: {', '.join(AUTO_FIX_POLICY.keys())}. "
                    f"Heartbeat: {'vivo' if alive else 'MORTO'}. "
                    f"Manutencao: {'ON' if self.maintenance.is_set() else 'OFF'}.")
        lines = ["RELATORIO DE AUTONOMIA v2 (recentes)"]
        for t, code, ok in self.history[-20:]:
            ts = datetime.fromtimestamp(t).strftime("%H:%M")
            lines.append(f"  {ts} Â· {code} Â· {'OK resolvido' if ok else 'FALHOU (escalado)'}")
        fixes = sum(1 for _, _, ok in self.history if ok)
        hour = len([1 for t, _, _ in self.history if time.time() - t < 3600])
        lines.append(
            f"Total: {fixes} resolvidos, {len(self.history) - fixes} escalados. "
            f"Breaker: {hour}/{MAX_FIXES_PER_HOUR}/h. "
            f"Estado: {'LIGADA' if self.enabled.is_set() else 'DESLIGADA'}. "
            f"Manutencao: {'ON' if self.maintenance.is_set() else 'OFF'}. "
            f"Heartbeat: {'vivo' if alive else 'MORTO'}."
        )
        return "\n".join(lines)

    def last_postmortem(self) -> str:
        pm = self.root / "logs_supervisor" / "postmortems"
        if not pm.exists():
            return "Nenhum post-mortem ainda."
        files = sorted(pm.glob("PM_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return "Nenhum post-mortem ainda."
        try:
            return files[0].read_text(encoding="utf-8")[:4000]
        except Exception as e:
            return f"Erro a ler post-mortem: {e}"

    def is_alive(self) -> bool:
        return (time.time() - self.last_beat) < (CYCLE_S * 3) and (
            self._thread is not None and self._thread.is_alive()
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        def loop():
            logger.info(
                "AUTONOMY ENGINE v2 ativo (radar %ss, politica %s codigos, RCA+janitor+preditivo)",
                CYCLE_S, len(AUTO_FIX_POLICY),
            )
            while True:
                try:
                    self._cycle()
                except Exception as e:
                    logger.error("autonomy_cycle_error %s", e)
                time.sleep(CYCLE_S)
        self._thread = threading.Thread(target=loop, daemon=True, name="aura-autonomy")
        self._thread.start()
        self.last_beat = time.time()


AUTONOMY: Optional[AutonomyEngine] = None


