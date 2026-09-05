from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    RICH = True
    console = Console(highlight=False, soft_wrap=True)
except ImportError:
    RICH = False
    console = None

# ============================================================
# Harness / AURA Supervisor Pro
# Chat determinístico + Ollama rápido + confirmação humana.
# Não armazena chaves e não executa reparo automaticamente.
# ============================================================

# Padrões seguros: o arquivo é executável sozinho e nunca inicia em modo real.
os.environ.setdefault("PAPER_TRADE", "true")
os.environ.setdefault("EXECUTION_ALLOWED", "false")
os.environ.setdefault("AURA_EXECUTION_ALLOWED", "0")
os.environ.setdefault("AURA_UNLOCK_LIVE", "0")
os.environ.setdefault("AURA_PAPER_ONLY", "1")
os.environ.setdefault("GLM_ADVISORY_ONLY", "true")

MASTER_EXTRACTION_PROMPT = r"""
MODO AGENTE DE EXTRAÇÃO FLASHScore–SokkerPro:
Trate cada entrada como um pedido completo. Não faça entrevistas, não repita perguntas e não peça confirmação de dados já presentes. Faça no máximo uma pergunta apenas se a tarefa ou o evento forem totalmente impossíveis de identificar; caso contrário, continue e use null para ausências.

Objetivo: equalizar dados do Flashscore com o SokkerPro usando sokkerpro_match_id como chave mestre. Normalize equipes, competição, temporada, rodada e timestamp UTC. Preserve o nome original e o nome normalizado. Extraia sempre as categorias match_metadata, team_stats, player_performance, timeline, standings, h2h_and_form e odds_market.

Em team_stats preserve xG, posse decimal, tentativas, chutes no alvo/fora/bloqueados, faltas, escanteios, impedimentos, defesas, passes tentados/completos, desarmes, ataques, ataques perigosos e APPM, incluindo geral, primeiro tempo e segundo tempo quando disponíveis. Em player_performance preserve ID, nome, posição, titular/reserva, rating, minutos, gols, pênaltis, gol contra, assistências, chutes, passes, passes-chave, duelos e perdas de posse. Em timeline preserve substituições, cartões, gols e VAR. Em standings preserve geral, casa e fora com posição, jogos, V/E/D, GF/GA, saldo, pontos, forma e impacto ao vivo. Em h2h_and_form preserve H2H, forma em casa/fora, over-under e BTTS. Em odds_market preserve abertura/live 1X2, over-under, handicap asiático e queda de odds.

Converta percentuais para decimal, use UTC ISO-8601 e calcule APPM somente com ataques perigosos e minutos conhecidos. Prefira Flashscore para estatísticas de jogo e SokkerPro para ID e odds de abertura. Registre conflitos, ausências, nomes não mapeados e confiança. Nunca force pareamento ambíguo: use AMBIGUOUS_MATCH_ERROR. Use PARTIAL_MATCH para evento identificado com campos incompletos e MISSING_SOURCE_DATA quando faltar a fonte.

Retorne exclusivamente JSON válido, em array, sem Markdown ou explicações. Inclua todas as chaves mesmo quando o valor for null. Nunca alegue ter acessado sites, APIs ou bancos que não estejam representados na entrada. Nunca faça upsert, scraping, instalação ou alteração sem aprovação explícita do Harness.
"""

AURA_ROOT = Path(os.environ.get("AURA_ROOT", r"C:\\aura"))
OLLAMA_URL = os.environ.get("AURA_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("AURA_CHAT_MODEL", "qwen3:8b")
KEEP_ALIVE = os.environ.get("AURA_KEEP_ALIVE", "24h")
NUM_CTX = int(os.environ.get("AURA_NUM_CTX", "8192"))
NUM_PREDICT = int(os.environ.get("AURA_NUM_PREDICT", "4096"))
EMOJI = os.environ.get("AURA_EMOJI", "1") not in {"0", "false", "no"}

# Área controlada para operações administrativas. O modelo nunca recebe shell
# genérico: toda mutação passa por um plano, aprovação exata, backup e auditoria.
CONTROL_ROOT = AURA_ROOT / "halem_control"
STAGING_ROOT = CONTROL_ROOT / "staging"
BACKUP_ROOT = CONTROL_ROOT / "backups"
AUDIT_LOG = CONTROL_ROOT / "audit.jsonl"
PLANS_FILE = CONTROL_ROOT / "plans.json"
AGENTS_ROOT = AURA_ROOT / "agents"
SKILLS_ROOT = AURA_ROOT / "skills"
ALLOWED_REPO_HOSTS = {"github.com", "gitlab.com", "codeberg.org"}
READABLE_EXTENSIONS = {".txt", ".html", ".htm", ".json", ".csv", ".md", ".log"}
MAX_READ_BYTES = 5 * 1024 * 1024
MAX_MODEL_FILE_CHARS = 50000
STATE_FILE = CONTROL_ROOT / "runtime" / "operational_state.json"
STATE_PREVIOUS_FILE = CONTROL_ROOT / "runtime" / "operational_state.previous.json"
INSTANCE_LOCK_FILE = CONTROL_ROOT / "runtime" / "harness.lock"
STATE_SCHEMA_VERSION = 1
GLOBAL_STATES = {"IDLE", "AWAITING_CONFIRMATION", "STARTING_STACK", "STACK_RUNNING", "DEGRADED", "RECOVERING", "ERROR", "STOPPING"}
COMPONENT_STATES = {"UNKNOWN", "DISCOVERED", "CONFIGURED", "STARTING", "PROCESS_RUNNING", "PORT_OPEN", "HEALTH_CHECKING", "READY", "DEGRADED", "STOPPING", "STOPPED", "FAILED", "BLOCKED"}
EVENT_NAMES = {"ACTION_REQUESTED", "CONFIRMATION_ACCEPTED", "CONFIRMATION_CANCELLED", "PROCESS_STARTED", "PROCESS_ALIVE", "PROCESS_EXITED", "PORT_OPEN", "PORT_CLOSED", "HEALTH_OK", "HEALTH_LOADING", "HEALTH_FAILED", "RECOVERY_REQUESTED", "RECOVERY_SUCCEEDED", "RECOVERY_LIMIT_REACHED", "OPERATION_COMPLETED", "OPERATION_FAILED"}


def _component_record(name: str, port: int | None = None, health_path: str | None = None) -> dict:
    return {"name": name, "state": "UNKNOWN", "port": port, "health_path": health_path, "pid": None,
            "owned_by_harness": False, "last_check_at": None, "last_error": None}


class OperationalStateStore:
    """Estado operacional durável; eventos e transições passam por este controlador."""
    def __init__(self, root: Path):
        self.root = root
        self.runtime = root / "halem_control" / "runtime"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.path = self.runtime / "operational_state.json"
        self.previous = self.runtime / "operational_state.previous.json"
        self.lock_path = self.runtime / "harness.lock"
        self.instance_id = f"harness-{os.getpid()}-{int(time.time())}"
        self.lock_owned = False
        self.state = self._load()
        policy = self.state.get("policy", {})
        if not (policy.get("paper_trade") is True and policy.get("execution_allowed") is False and
                policy.get("aura_execution_allowed") is False and policy.get("aura_unlock_live") is False):
            self.state["global_state"] = "ERROR"
            self.state["last_error"] = {"code": "SAFETY_POLICY_VIOLATION", "message": "política persistida inválida"}
            self.save()

    def acquire(self) -> bool:
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "instance_id": self.instance_id, "created_at": utc_now()}).encode())
            os.close(fd)
            self.lock_owned = True
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        if self.lock_owned:
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.lock_owned = False

    def _default(self) -> dict:
        definitions = {
            "ollama": (11434, "/api/tags"), "engine": (8765, "/api/health"),
            "bridge": (8080, "/health"), "voice": (8099, "/api/voice/health"),
            "hermes": (8765, None), "alfred": (8791, None), "desktop": (None, None),
        }
        components = {name: _component_record(name, port, health) for name, (port, health) in definitions.items()}
        components["hermes"]["state"] = "BLOCKED"
        return {"schema_version": STATE_SCHEMA_VERSION, "instance_id": self.instance_id, "updated_at": utc_now(),
                "global_state": "IDLE", "pending_action": None, "current_operation": None, "components": components,
                "policy": {"paper_trade": True, "execution_allowed": False, "aura_execution_allowed": False, "aura_unlock_live": False},
                "recovery": {"attempts": {}, "window_seconds": 300, "max_attempts": 3}, "last_operation": None, "last_error": None}

    def _load(self) -> dict:
        for candidate in (self.path, self.previous):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if data.get("schema_version") == STATE_SCHEMA_VERSION and isinstance(data.get("components"), dict):
                    return data
            except (OSError, json.JSONDecodeError, TypeError):
                continue
        return self._default()

    def save(self) -> None:
        self.state["updated_at"] = utc_now()
        self.state["instance_id"] = self.instance_id
        payload = json.dumps(self.state, ensure_ascii=False, indent=2)
        temporary = self.path.with_suffix(".json.tmp")
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.previous)
            except OSError:
                pass
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, self.path)

    def transition(self, event: str, component: str | None = None, to_state: str | None = None, **metadata) -> dict:
        if event not in EVENT_NAMES:
            raise ValueError(f"evento inválido: {event}")
        if component:
            item = self.state["components"].setdefault(component, _component_record(component))
            old_state = item.get("state", "UNKNOWN")
            if to_state and to_state not in COMPONENT_STATES:
                raise ValueError(f"estado de componente inválido: {to_state}")
            if to_state:
                item["state"] = to_state
            item["last_check_at"] = utc_now()
            item.update({key: value for key, value in metadata.items() if value is not None})
            if event in {"HEALTH_FAILED", "PROCESS_EXITED"}:
                item["last_error"] = metadata.get("error", event)
            audit("state_transition", component=component, from_state=old_state, to_state=item["state"], trigger=event, **metadata)
        else:
            old_state = self.state.get("global_state", "IDLE")
            if to_state and to_state not in GLOBAL_STATES:
                raise ValueError(f"estado global inválido: {to_state}")
            if to_state:
                self.state["global_state"] = to_state
            audit("state_transition", from_state=old_state, to_state=self.state.get("global_state"), trigger=event, **metadata)
        self.save()
        return self.state

if KEEP_ALIVE in {"0", "0s", "0m"}:
    raise RuntimeError("AURA_KEEP_ALIVE não pode ser zero.")

SERVICES = {
    "ollama": ("127.0.0.1", 11434, "/api/tags"),
    "engine": ("127.0.0.1", 8765, "/api/health"),
    "bridge": ("127.0.0.1", 8080, "/health"),
    "voice": ("127.0.0.1", 8099, "/api/voice/health"),
}

# Ações disponíveis. Ações com efeito exigem confirmação textual exata.
MUTATING_ACTIONS = {
    "desativar segura": "Desativar a AURA somente por inicializador oficial validado, mantendo execução real bloqueada.",
    "reiniciar aura": "Reiniciar a AURA somente por inicializador oficial validado, preservando o estado seguro.",
    "auditar aura": "Coletar diagnóstico, saúde dos serviços, política e trilha de auditoria sem alterar arquivos.",
    "manutencao segura": "Executar verificação de manutenção somente leitura e propor correções verificáveis.",
    "corrigir auditavel": "Diagnosticar e preparar correções com backup, validação e rollback; não apagar nem alterar sem aprovação.",
    "reparar seguro": "Diagnosticar problemas e propor um plano verificável; nenhuma alteração é feita nesta etapa.",
    "criar agente": "Criar um manifesto de agente em área controlada, sem ativá-lo automaticamente.",
    "instalar skill": "Baixar uma skill para staging, registrar a origem e validar arquivos antes de promover.",
    "instalar repositorio": "Baixar um repositório para staging para inspeção; não executar setup.py, Makefile ou scripts externos.",
    "treinar agente": "Registrar uma sessão supervisionada de treinamento; não altera pesos nem executa código externo.",
    "ativar segura": "Ativar agentes pela API segura, mantendo paper trade e execução real desativada.",
    "iniciar engine": "Iniciar o servidor Engine local na porta 8765.",
    "iniciar bridge": "Iniciar o Bridge local na porta 8080.",
    "iniciar voice": "Iniciar o servidor Voice local na porta 8099.",
    "reiniciar engine": "Reiniciar o servidor Engine local.",
    "reiniciar bridge": "Reiniciar o Bridge local.",
    "reiniciar voice": "Reiniciar o servidor Voice local.",
    "iniciar stack": "Iniciar Engine, Bridge e Voice e validar health checks.",
    "abrir aura": "Abrir a interface/Desktop oficial da AURA quando disponível.",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.strip().lower())


def out(text: str, style: str = "white") -> None:
    if RICH:
        console.print(text, style=style)
    else:
        print(text)


def print_complete(text: str) -> None:
    """Exibe toda a resposta no terminal, sem corte visual do painel."""
    if not text:
        return
    chunk_size = 5000
    parts = []
    remaining = text
    while len(remaining) > chunk_size:
        cut = remaining.rfind("\n", 0, chunk_size)
        if cut < 1000:
            cut = chunk_size
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    parts.append(remaining)
    if RICH and len(parts) > 1:
        for index, part in enumerate(parts, 1):
            console.print(f"[bold cyan]Harness — parte {index}/{len(parts)}[/bold cyan]")
            console.print(part, markup=False, soft_wrap=True)
    elif RICH:
        console.print(text, markup=False, soft_wrap=True)
    else:
        print(text)


def title(text: str) -> None:
    if RICH:
        console.print(Panel.fit(text, border_style="cyan", title="[bold cyan]AURA / Harness[/bold cyan]"))
    else:
        print("=" * 60)
        print(text)
        print("=" * 60)


def http_json(url: str, timeout: float = 1.8):
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = raw[:500]
            return {"online": True, "status": response.status, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "data": data}
    except Exception as exc:
        return {"online": False, "error": str(exc)}


def tcp_check(host: str, port: int, timeout: float = 0.35):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "path": str(path)}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_control_dirs() -> None:
    for path in (CONTROL_ROOT, STAGING_ROOT, BACKUP_ROOT, AGENTS_ROOT, SKILLS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def audit(event: str, **details) -> None:
    ensure_control_dirs()
    record = {"timestamp": utc_now(), "event": event, **details}
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\\n")


def safe_name(value: str) -> str:
    value = normalize(value).replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,48}", value):
        raise ValueError("nome inválido; use 2–49 caracteres alfanuméricos, hífen ou sublinhado")
    return value


def load_plans() -> list[dict]:
    data = read_json(PLANS_FILE)
    return data if isinstance(data, list) else []


def save_plan(kind: str, title_text: str, payload: dict) -> str:
    ensure_control_dirs()
    plan_id = f"p-{int(time.time())}-{hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:8]}"
    plan = {"id": plan_id, "kind": kind, "title": title_text, "status": "PENDENTE", "created_at": utc_now(), "payload": payload}
    plans = load_plans()
    plans.append(plan)
    PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
    audit("plan_created", plan_id=plan_id, kind=kind, payload=payload)
    return plan_id


def _normalized_filename(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def find_aura_files(query: str) -> list[Path]:
    root = AURA_ROOT.resolve()
    needle = _normalized_filename(query).replace("_", " ")
    candidates = []
    for path in root.rglob("*"):
        try:
            resolved = path.resolve()
            if not path.is_file() or root not in resolved.parents or path.suffix.lower() not in READABLE_EXTENSIONS:
                continue
            haystack = _normalized_filename(path.name).replace("_", " ")
            score = sum(1 for token in needle.split() if len(token) > 2 and token in haystack)
            if score:
                candidates.append((score, len(path.name), path))
        except OSError:
            continue
    return [item[2] for item in sorted(candidates, key=lambda item: (-item[0], item[1]))[:5]]


def read_aura_file(path: Path) -> str:
    root = AURA_ROOT.resolve()
    path = path.resolve()
    if root not in path.parents or path.suffix.lower() not in READABLE_EXTENSIONS:
        raise ValueError("arquivo fora da área ou formato não permitido")
    if path.stat().st_size > MAX_READ_BYTES:
        raise ValueError("arquivo excede o limite de leitura de 5 MB")
    return path.read_text(encoding="utf-8", errors="replace")[:MAX_MODEL_FILE_CHARS]


def repo_url(raw: str) -> str:
    parsed = urllib.parse.urlparse(raw.strip())
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_REPO_HOSTS or parsed.query or parsed.fragment:
        raise ValueError("repositório permitido somente via HTTPS em GitHub, GitLab ou Codeberg")
    return raw.strip().rstrip("/")


def agent_manifest_path(name: str) -> Path:
    agent = safe_name(name)
    target = (AGENTS_ROOT / agent / "agent.json").resolve()
    if AGENTS_ROOT.resolve() not in target.parents or target.name != "agent.json":
        raise ValueError("destino de agente fora da área permitida")
    return target


def create_agent_manifest(name: str, purpose: str) -> tuple[str, str]:
    agent = safe_name(name)
    target = agent_manifest_path(agent)
    if target.exists():
        raise ValueError("agente já existe")
    manifest = {"name": agent, "purpose": purpose.strip()[:1000], "enabled": False, "capabilities": [], "approval_required": True, "created_at": utc_now()}
    return str(target), json.dumps(manifest, ensure_ascii=False, indent=2)


def collect_snapshot():
    services = {}
    for name, (host, port, health_path) in SERVICES.items():
        online = tcp_check(host, port)
        item = {"online": online, "port": port}
        if online:
            item["health"] = http_json(f"http://{host}:{port}{health_path}")
        services[name] = item

    diagnostic_path = AURA_ROOT / "state" / "diagnostico_latest.json"
    boot_path = AURA_ROOT / "engine" / "data" / "boot_state.json"
    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "keep_alive": KEEP_ALIVE,
        "num_ctx": NUM_CTX,
        "services": services,
        "diagnostic": read_json(diagnostic_path),
        "boot_state": read_json(boot_path),
        "operational_state": read_json(STATE_FILE),
        "policy": {
            "read_only_default": True,
            "confirmation_required": True,
            "paper_trade": True,
            "execution_allowed": False,
            "repair": "disabled",
        },
    }


def snapshot_summary(snapshot: dict) -> str:
    services = snapshot.get("services", {})
    lines = []
    for name, item in services.items():
        state = "ONLINE" if item.get("online") else "OFFLINE"
        latency = item.get("health", {}).get("latency_ms", "-") if item.get("online") else "-"
        lines.append(f"{name.upper()}: {state} porta={item.get('port')} latência={latency}ms")
    boot = snapshot.get("boot_state", {})
    boot_state = boot.get("running", "não confirmado") if isinstance(boot, dict) else "não confirmado"
    operational = snapshot.get("operational_state", {})
    global_state = operational.get("global_state", "não persistido") if isinstance(operational, dict) else "não persistido"
    return "\n".join(lines) + f"\nBOOT_RUNNING: {boot_state}\nOPERATIONAL_STATE: {global_state}\nPOLICY: paper_trade=true; execution_allowed=false; repair=disabled"


def show_status(snapshot: dict) -> None:
    if RICH:
        table = Table(title="Estado da AURA", border_style="cyan", show_lines=False)
        table.add_column("Serviço", style="bold")
        table.add_column("Estado")
        table.add_column("Porta", justify="right")
        table.add_column("Latência", justify="right")
        for name, item in snapshot["services"].items():
            online = item.get("online", False)
            table.add_row(name.upper(), "🟢 ONLINE" if online else "🔴 OFFLINE", str(item["port"]), str(item.get("health", {}).get("latency_ms", "-")))
        console.print(table)
        console.print(Panel.fit(f"Modelo: {MODEL}\nRetenção: {KEEP_ALIVE}\nContexto: {NUM_CTX}\nPaper trade: ativo\nExecução real: bloqueada", title="Configuração", border_style="green"))
    else:
        print(snapshot_summary(snapshot))


def compact_context(snapshot: dict) -> str:
    # Evita enviar diagnósticos gigantes em toda pergunta; reduz prefill e latência.
    return json.dumps({
        "services": snapshot["services"],
        "boot_state": snapshot["boot_state"],
        "policy": snapshot["policy"],
        "model": snapshot["model"],
        "keep_alive": snapshot["keep_alive"],
        "num_ctx": snapshot["num_ctx"],
    }, ensure_ascii=False, separators=(",", ":"))[:12000]


async def ask_ollama(user_text: str, snapshot: dict) -> str:
    system = (
        MASTER_EXTRACTION_PROMPT + "\n"
        "Você é o Harness, agente supervisor da AURA. HALem é o usuário e responsável pelas aprovações. Converse em português natural, como um "
        "agente útil e direto. Entenda pedidos informais e não exija comandos exatos. "
        "Se o usuário colar uma especificação longa, trate-a como um único pedido completo: "
        "resuma o objetivo, proponha uma ação consolidada e não faça questionário. Faça no máximo "
        "uma pergunta apenas se faltar um dado indispensável. Nunca invente estado nem diga que "
        "executou algo que não foi executado. Para mudanças, encaminhe para uma única aprovação. "
        "Não repita diagnósticos, listas ou recomendações genéricas. Máximo de 4 linhas."
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"CONTEXTO:\n{compact_context(snapshot)}\n\nPEDIDO:\n{user_text}"},
        ],
        "stream": True,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_gpu": 99, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT, "temperature": 0.15},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks = []
    started = time.perf_counter()
    try:
        response = await asyncio.to_thread(urllib.request.urlopen, request, timeout=90)
        try:
            while True:
                line = await asyncio.to_thread(response.readline)
                if not line:
                    break
                part = json.loads(line.decode("utf-8", errors="replace"))
                message = part.get("message", {})
                text = message.get("content", "")
                if text:
                    chunks.append(text)
                if part.get("done"):
                    break
        finally:
            response.close()
    except Exception as exc:
        return f"❌ Falha no Ollama: {exc}"
    result = "".join(chunks).strip() or "NÃO CONFIRMADO"
    elapsed = time.perf_counter() - started
    return f"{result}\n\n[dim]⏱ {elapsed:.1f}s · chamada única · modelo residente[/dim]" if RICH else f"{result}\n[tempo: {elapsed:.1f}s]"


class AuraServiceManager:
    """Gerenciador determinístico dos serviços oficiais da AURA."""
    def __init__(self, root: Path, state: OperationalStateStore | None = None):
        self.root=root; self.runtime=CONTROL_ROOT/"runtime"; self.runtime.mkdir(parents=True, exist_ok=True)
        self.state = state
        py=sys.executable
        self.specs={
          "engine":{"port":8765,"health":"/api/health","cmd":[py,str(root/"engine"/"server.py")],"cwd":root/"engine","timeout":45},
          "bridge":{"port":8080,"health":"/health","cmd":[py,str(root/"bridge"/"server.py")],"cwd":root/"bridge","timeout":45},
          "voice":{"port":8099,"health":"/api/voice/health","cmd":[py,str(root/"bridge"/"jarvis_voice_server.py")],"cwd":root/"bridge","timeout":75},
        }
        self.processes={}

    def _health(self,name):
        x=self.specs[name]; return http_json(f"http://127.0.0.1:{x['port']}{x['health']}",3.0).get("online",False)
    def status(self,name):
        x=self.specs[name]; return {"service":name,"port":x['port'],"port_open":tcp_check("127.0.0.1",x['port']),"healthy":self._health(name)}
    def _tail(self,path,n=35):
        if not path.exists(): return "log não criado"
        return "\\n".join(path.read_text(encoding="utf-8",errors="replace").splitlines()[-n:])
    def start(self,name):
        x=self.specs[name]
        if self._health(name):
            if self.state: self.state.transition("HEALTH_OK", name, "READY", owned_by_harness=False, port=x["port"])
            return {"ok":True,"service":name,"status":"already_online","port":x['port']}
        if not x['cmd'] or not Path(x['cmd'][1]).exists(): return {"ok":False,"service":name,"error":"entrypoint ausente"}
        logp=self.runtime/f"{name}.log"; log=open(logp,"a",encoding="utf-8",errors="replace")
        log.write(f"\n===== START {name} {utc_now()} =====\n"); log.flush()
        kwargs={"cwd":str(x['cwd']),"stdout":log,"stderr":subprocess.STDOUT,"shell":False}
        if os.name=="nt": kwargs["creationflags"]=getattr(subprocess,"CREATE_NO_WINDOW",0x08000000)
        if self.state: self.state.transition("ACTION_REQUESTED", name, "STARTING", owned_by_harness=True)
        proc=subprocess.Popen(x['cmd'],**kwargs); self.processes[name]=proc
        if self.state: self.state.transition("PROCESS_STARTED", name, "PROCESS_RUNNING", pid=proc.pid, owned_by_harness=True)
        end=time.time()+x['timeout']
        while time.time()<end:
            if self._health(name):
                if self.state: self.state.transition("HEALTH_OK", name, "READY", pid=proc.pid, owned_by_harness=True)
                return {"ok":True,"service":name,"status":"started","pid":proc.pid,"port":x['port'],"log":str(logp)}
            if tcp_check("127.0.0.1", x["port"]):
                if self.state: self.state.transition("PORT_OPEN", name, "PORT_OPEN", pid=proc.pid, owned_by_harness=True)
            if proc.poll() is not None:
                if self.state: self.state.transition("PROCESS_EXITED", name, "FAILED", pid=proc.pid, error=f"exit_code={proc.returncode}")
                return {"ok":False,"service":name,"status":"process_exited","exit_code":proc.returncode,"log":self._tail(logp)}
            time.sleep(1)
        if self.state: self.state.transition("HEALTH_FAILED", name, "DEGRADED", pid=proc.pid, error="HEALTH_TIMEOUT")
        return {"ok":False,"service":name,"status":"timeout","pid":proc.pid,"port":x['port'],"log":self._tail(logp)}
    def stop(self,name):
        proc=self.processes.get(name)
        if proc and proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=8)
            except subprocess.TimeoutExpired: proc.kill()
            if self.state: self.state.transition("OPERATION_COMPLETED", name, "STOPPED", pid=proc.pid, owned_by_harness=True)
            return {"ok":True,"service":name,"status":"stopped"}
        return {"ok":False,"service":name,"status":"process_not_owned"}
    def start_stack(self):
        results=[]
        for name in ("engine","bridge","voice"):
            r=self.start(name); results.append(r)
            if not r.get("ok"): return {"ok":False,"failed":name,"results":results}
        return {"ok":True,"results":results}

class Halem:
    def __init__(self):
        self.running = True
        self.in_chat = False
        self.pending_action: str | None = None
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.model_lock = asyncio.Lock()
        self.dialogue: str | None = None
        self.clarification_used = False
        self.state = OperationalStateStore(AURA_ROOT)
        self.lock_available = self.state.acquire()
        self.services = AuraServiceManager(AURA_ROOT, self.state)

    def intent(self, raw: str):
        text = normalize(raw)
        if text in {"sair", "exit", "quit"}:
            return "exit", None
        # Especificações extensas devem ser tratadas como um único pedido, não como
        # conversa de descoberta. Isso evita loops causados por prompts colados.
        if len(raw) >= 900 or ("# role" in text and "# objective" in text):
            return "full_spec", raw.strip()
        if text in {"chat", "conversar"}:
            return "chat", None
        if text in {"status", "estado", "diagnostico", "diagnostico completo"}:
            return "status", None
        if any(phrase in text for phrase in ("auditar aura", "auditoria", "faça uma auditoria", "faca uma auditoria", "audite o sistema")):
            return "action", "auditar aura"
        if any(phrase in text for phrase in ("manutenção", "manutencao", "verificação de manutenção", "verificacao de manutencao")):
            return "action", "manutencao segura"
        if any(phrase in text for phrase in ("corrija a aura", "corrigir a aura", "repare a aura", "reparar a aura", "corrija isso", "reparo seguro")):
            return "action", "corrigir auditavel"
        if any(phrase in text for phrase in ("desative a aura", "desativar a aura", "desligue a aura", "desligar a aura")):
            return "action", "desativar segura"
        if any(phrase in text for phrase in ("reinicie a aura", "reiniciar a aura", "reinicie tudo", "reiniciar tudo")):
            return "action", "reiniciar aura"
        if any(phrase in text for phrase in ("abrir arquivo", "abra o arquivo", "ler arquivo", "leia o arquivo", "carregar arquivo", "analise o arquivo", "analisar o arquivo")):
            return "read_file", raw.strip()
        if any(phrase in text for phrase in ("instalar agente", "instale um agente", "baixar agente", "adicionar agente", "instala um agente")):
            return "agent_installer", raw.strip()
        if any(phrase in text for phrase in ("criar novos agentes", "construir novos agentes", "criar um agente", "construir um agente", "novo agente", "novos agentes")):
            return "agent_builder", raw.strip()
        if text in {"ajuda", "help", "comandos"}:
            return "help", None
        if text in {"reparar", "diagnosticar reparo", "plano de reparo"}:
            return "repair_plan", None
        if text.startswith("criar agente "):
            return "create_agent", text.removeprefix("criar agente ").strip()
        if text.startswith("editar agente "):
            return "edit_agent", text.removeprefix("editar agente ").strip()
        if text.startswith("ordenar tarefas "):
            return "order_tasks", text.removeprefix("ordenar tarefas ").strip()
        if text.startswith("instalar skill "):
            return "install_skill", text.removeprefix("instalar skill ").strip()
        if text.startswith("instalar repositorio "):
            return "install_repo", text.removeprefix("instalar repositorio ").strip()
        if text.startswith("treinar agente "):
            return "train_agent", text.removeprefix("treinar agente ").strip()
        if text in {"cancelar", "cancela", "nao", "não"}:
            return "cancel", None
        if text.startswith("confirmar "):
            return "confirm", text.removeprefix("confirmar ").strip()

        # Compreende pedidos naturais de inicialização antes de chamar o modelo.
        if text in {"sim", "confirmo", "confirmado", "pode", "prossiga", "continue", "ok", "okay"} and self.pending_action:
            return "confirm", self.pending_action
        if any(phrase in text for phrase in ("inicie o aura", "iniciar o aura", "ligue o aura", "ligar o aura", "inicie aura", "ligue tudo", "ative tudo", "iniciar sistema aura", "iniciar sistema", "ligue os servicos", "iniciar os servicos", "iniciar todos os servicos")):
            return "action", "iniciar stack"
        if any(phrase in text for phrase in ("abra aura", "abra o aura", "abrir aura", "abra o desktop", "abrir o desktop", "quero operar")):
            return "action", "abrir aura"
        for service in ("engine", "bridge", "voice"):
            if any(phrase in text for phrase in (f"reiniciar {service}", f"reinicie {service}", f"restart {service}")):
                return "action", f"reiniciar {service}"
            if any(phrase in text for phrase in (f"iniciar {service}", f"inicie {service}", f"ligar {service}", f"liga {service}", f"ative {service}")):
                return "action", f"iniciar {service}"
        if text == "ativar segura":
            return "action", text
        return "model", None

    def help(self):
        return (                "Comandos: status · chat · ajuda · reparar · criar agente NOME: OBJETIVO · "
                "editar agente NOME: CAMPO=VALOR · ordenar tarefas NOME: T1 > T2 · "
                "instalar skill URL · instalar repositorio URL · treinar agente NOME · "

                "inicie o aura · ativar segura · cancelar · sair\\n"
                "Operações administrativas geram plano, ficam em staging e exigem confirmação exata. "
                "Código externo nunca é executado automaticamente.")

    def ask_plan(self, kind: str, title_text: str, payload: dict):
        try:
            plan_id = save_plan(kind, title_text, payload)
        except ValueError as exc:
            return f"❌ Plano rejeitado: {exc}"
        self.pending_action = f"plano {plan_id}"
        return (f"⚠️ PLANO PENDENTE {plan_id}\\n{title_text}\\n"
                f"Payload: {json.dumps(payload, ensure_ascii=False)}\\n\\n"
                f"Nada foi alterado. Digite exatamente: CONFIRMAR {self.pending_action.upper()}\\n"
                "Ou digite CANCELAR.")

    async def prepare_full_spec(self, specification: str):
        title_line = next((line.strip() for line in specification.splitlines() if line.strip().lower().startswith(("# objective", "# objetivo"))), "Especificação de novo agente")
        purpose = specification[:5000]
        name = f"agente-especificacao-{int(time.time())}"
        target = AGENTS_ROOT / name / "agent.json"
        manifest = {"name": name, "purpose": title_line, "enabled": False, "approval_required": True, "instructions": purpose, "tasks": [], "created_at": utc_now()}
        return self.ask_plan("create_agent", "Preparar agente a partir da especificação completa", {"target": str(target), "content": json.dumps(manifest, ensure_ascii=False, indent=2), "source": "prompt_completo", "single_approval": True})

    async def prepare_natural_install(self, request: str):
        urls = re.findall(r"https://(?:github\\.com|gitlab\\.com|codeberg\\.org)/[^\\s]+", request)
        if not urls:
            self.dialogue = "install_agent"
            return ("Para instalar o agente, preciso de apenas uma coisa: envie o link HTTPS do repositório "
                    "junto com o nome ou objetivo desejado, tudo na mesma mensagem.")
        url = urls[0].rstrip(".,);]")
        try:
            url = repo_url(url)
        except ValueError as exc:
            return f"❌ Não posso usar esse link: {exc}"
        label = safe_name(request.replace(url, "").strip() or f"agente-{int(time.time())}")
        return self.ask_plan("install_repo", "Instalar agente em staging para revisão", {"url": url, "agent": label, "execute_installers": False, "single_approval": True})

    async def administrative_plan(self, kind: str, value: str):
        if kind == "repair_plan":
            snapshot = await asyncio.to_thread(collect_snapshot)
            return self.ask_plan("repair", "Diagnóstico controlado; sem mutação", {"snapshot": snapshot})
        if kind == "create_agent":
            if ":" not in value:
                return "Formato: criar agente NOME: OBJETIVO"
            name, purpose = value.split(":", 1)
            try:
                target, content = create_agent_manifest(name.strip(), purpose.strip())
            except ValueError as exc:
                return f"❌ Não foi possível preparar o agente: {exc}"
            return self.ask_plan("create_agent", "Criar manifesto desativado", {"target": target, "content": content})
        if kind == "edit_agent":
            if ":" not in value or "=" not in value:
                return "Formato: editar agente NOME: CAMPO=VALOR"
            name, assignment = value.split(":", 1)
            field, new_value = assignment.split("=", 1)
            field = normalize(field)
            allowed = {"purpose", "capabilities", "instructions", "tasks"}
            if field not in allowed:
                return f"❌ Campo não permitido. Use: {', '.join(sorted(allowed))}."
            try:
                target = agent_manifest_path(name.strip())
            except ValueError as exc:
                return f"❌ Agente rejeitado: {exc}"
            if not target.exists():
                return "❌ Manifesto do agente não existe."
            return self.ask_plan("edit_agent", "Editar campo declarativo do agente", {"target": str(target), "field": field, "value": new_value.strip()})
        if kind == "order_tasks":
            if ":" not in value:
                return "Formato: ordenar tarefas NOME: T1 > T2 > T3"
            name, tasks = value.split(":", 1)
            ordered = [item.strip() for item in tasks.split(">") if item.strip()]
            if not ordered or len(ordered) != len(set(ordered)):
                return "❌ A ordem precisa conter tarefas únicas e não vazias."
            try:
                target = agent_manifest_path(name.strip())
            except ValueError as exc:
                return f"❌ Agente rejeitado: {exc}"
            if not target.exists():
                return "❌ Manifesto do agente não existe."
            return self.ask_plan("order_tasks", "Ordenar tarefas do agente", {"target": str(target), "tasks": ordered})
        if kind == "install_repo":
            try:
                url = repo_url(value)
            except ValueError as exc:
                return f"❌ Origem rejeitada: {exc}"
            return self.ask_plan("install_repo", "Baixar para staging para revisão manual", {"url": url, "execute_installers": False})
        if kind == "install_skill":
            try:
                url = repo_url(value)
            except ValueError as exc:
                return f"❌ Origem rejeitada: {exc}"
            return self.ask_plan("install_skill", "Baixar skill para staging para revisão manual", {"url": url, "execute_installers": False})
        if kind == "train_agent":
            name = safe_name(value)
            return self.ask_plan("train_agent", "Registrar treinamento supervisionado", {"agent": name, "mode": "supervised", "change_weights": False})
        return "❌ Operação administrativa desconhecida."

    def ask_confirmation(self, action: str):
        self.pending_action = action
        self.state.state["pending_action"] = {"intent": action.upper().replace(" ", "_"), "action": action, "created_at": utc_now()}
        self.state.transition("ACTION_REQUESTED", to_state="AWAITING_CONFIRMATION", action=action)
        description = MUTATING_ACTIONS.get(action, "Ação operacional")
        text = f"⚠️ AÇÃO PENDENTE\n{description}\n\nNada foi executado. Digite exatamente:\nCONFIRMAR {action.upper()}\n\nOu digite CANCELAR."
        return text

    async def run_safe_activation(self):
        script = AURA_ROOT / "scripts" / "aura_activate_safe.py"
        if not script.exists():
            return "❌ Ação não executada: aura_activate_safe.py não encontrado."
        env = os.environ.copy()
        env.update({"PAPER_TRADE": "true", "EXECUTION_ALLOWED": "false", "AURA_EXECUTION_ALLOWED": "0", "AURA_UNLOCK_LIVE": "0", "AURA_PAPER_ONLY": "1", "GLM_ADVISORY_ONLY": "true"})
        try:
            result = await asyncio.to_thread(subprocess.run, [sys.executable, str(script)], cwd=str(AURA_ROOT), env=env, capture_output=True, text=True, timeout=30)
            return f"✅ Ativação segura concluída. código={result.returncode}\n{result.stdout[-2500:]}"
        except Exception as exc:
            return f"❌ Ativação segura falhou: {exc}"

    async def execute(self, action: str):
        if action == "iniciar stack":
            self.state.state["pending_action"] = None
            self.state.state["current_operation"] = {"intent": "START_STACK", "started_at": utc_now()}
            self.state.transition("CONFIRMATION_ACCEPTED", to_state="STARTING_STACK", action=action)
            result = await asyncio.to_thread(self.services.start_stack)
            audit("stack_start", result=result)
            if result.get("ok"):
                self.state.state["current_operation"] = None
                self.state.state["last_operation"] = {"intent": "START_STACK", "result": "SUCCESS", "finished_at": utc_now()}
                self.state.transition("OPERATION_COMPLETED", to_state="STACK_RUNNING", action=action)
                lines=["🚀 AURA STACK ONLINE"]
                for r in result["results"]: lines.append(f"🟢 {r['service'].title()} · porta {r['port']} · {r['status']}" )
                return "\n".join(lines)
            failed=result.get("failed"); detail=result["results"][-1]
            self.state.state["current_operation"] = None
            self.state.state["last_operation"] = {"intent": "START_STACK", "result": "DEGRADED", "failed": failed, "finished_at": utc_now()}
            self.state.transition("OPERATION_FAILED", to_state="DEGRADED", action=action, error=detail.get("status") or detail.get("error"))
            return f"🔴 Falha ao iniciar {failed}.\nStatus: {detail.get('status') or detail.get('error')}\n📄 Log: {detail.get('log','não disponível')}"
        if action in {"iniciar engine", "iniciar bridge", "iniciar voice"}:
            name=action.split()[-1]; result=await asyncio.to_thread(self.services.start,name); audit("service_start",service=name,result=result)
            if result.get("ok"): return f"🟢 {name.title()} online · porta {result['port']} · {result['status']}"
            return f"🔴 {name.title()} falhou: {result.get('status') or result.get('error')}\n📄 {result.get('log','')}"
        if action in {"reiniciar engine", "reiniciar bridge", "reiniciar voice"}:
            name=action.split()[-1]; await asyncio.to_thread(self.services.stop,name); result=await asyncio.to_thread(self.services.start,name)
            return (f"🟢 {name.title()} reiniciado com sucesso." if result.get("ok") else f"🔴 Falha ao reiniciar {name}: {result}")
        if action == "abrir aura":
            candidates=[AURA_ROOT/"AURA_DESKTOP.exe", AURA_ROOT/"desktop"/"AURA_DESKTOP.exe", AURA_ROOT/"START_AURA.bat"]
            target=next((p for p in candidates if p.exists()),None)
            if not target: return "🟡 Desktop AURA não encontrado nos entrypoints oficiais conhecidos. Nenhum programa foi aberto."
            subprocess.Popen([str(target)],cwd=str(target.parent),shell=target.suffix.lower()==".bat")
            return f"🖥️ Abrindo AURA: {target.name}"
        if action == "ativar segura":
            return await self.run_safe_activation()
        if action == "auditar aura":
            snapshot = await asyncio.to_thread(collect_snapshot)
            audit("audit_completed", services=snapshot.get("services", {}), policy=snapshot.get("policy", {}))
            return "✅ Auditoria concluída sem alterações.\n" + snapshot_summary(snapshot)
        if action == "manutencao segura":
            snapshot = await asyncio.to_thread(collect_snapshot)
            audit("maintenance_check_completed", services=snapshot.get("services", {}))
            return ("✅ Verificação de manutenção concluída em modo somente leitura.\n" +
                    snapshot_summary(snapshot) +
                    "\nNenhum arquivo, processo ou configuração foi alterado.")
        if action == "corrigir auditavel":
            snapshot = await asyncio.to_thread(collect_snapshot)
            plan_id = save_plan("repair", "Correção auditável baseada no diagnóstico atual", {"snapshot": snapshot, "rollback_required": True})
            return (f"✅ Plano de correção criado: {plan_id}. Diagnóstico concluído; nenhuma alteração foi feita. "
                    "A execução só ocorrerá após aprovação do plano e validação de cada etapa.")
        if action in {"desativar segura", "reiniciar aura"}:
            return (f"⚠️ `{action}` foi recebido, mas permanece bloqueado porque ainda não há um inicializador oficial "
                    "validado para essa operação. Nenhum processo foi encerrado e nenhuma alteração foi feita.")
        if action.startswith("plano "):
            plan_id = action.removeprefix("plano ")
            plans = load_plans()
            plan = next((item for item in plans if item.get("id") == plan_id and item.get("status") == "PENDENTE"), None)
            if not plan:
                return "❌ Plano inexistente, expirado ou já processado."
            kind = plan.get("kind")
            payload = plan.get("payload", {})
            if kind == "create_agent":
                target = Path(payload["target"]).resolve()
                if AGENTS_ROOT.resolve() not in target.parents or target.name != "agent.json":
                    return "❌ Destino do agente rejeitado pela política de caminho."
                target.parent.mkdir(parents=True, exist_ok=True)
                backup = None
                if target.exists():
                    backup = BACKUP_ROOT / f"{target.stem}-{int(time.time())}.json"
                    shutil.copy2(target, backup)
                target.write_text(payload["content"], encoding="utf-8")
                plan["status"] = "APLICADO"
                plan["applied_at"] = utc_now()
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("agent_manifest_applied", plan_id=plan_id, target=str(target), backup=str(backup) if backup else None)
                return f"✅ Manifesto criado em área desativada: {target}. Backup: {backup or 'não necessário'}."
            if kind in {"edit_agent", "order_tasks"}:
                target = Path(payload["target"]).resolve()
                if AGENTS_ROOT.resolve() not in target.parents or target.name != "agent.json" or not target.exists():
                    return "❌ Destino do manifesto rejeitado pela política de caminho."
                try:
                    current = json.loads(target.read_text(encoding="utf-8"))
                except Exception as exc:
                    return f"❌ Manifesto inválido; nenhuma alteração feita: {exc}"
                backup = BACKUP_ROOT / f"{target.parent.name}-{int(time.time())}.json"
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                if kind == "edit_agent":
                    field = payload["field"]
                    value = payload["value"]
                    current[field] = [item.strip() for item in value.split(",") if item.strip()] if field in {"capabilities", "tasks"} else value
                else:
                    current["tasks"] = payload["tasks"]
                target.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
                plan["status"] = "APLICADO"
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("agent_manifest_updated", plan_id=plan_id, target=str(target), backup=str(backup), kind=kind)
                return f"✅ Manifesto atualizado com aprovação: {target}. Backup: {backup}."
            if kind in {"install_repo", "install_skill"}:
                plan["status"] = "STAGING_APROVADO"
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("external_source_approved_for_staging", plan_id=plan_id, url=payload.get("url"))
                return ("✅ Aprovação registrada para staging. O código ainda não foi instalado nem executado; "
                        "a revisão de arquivos, licença, dependências e assinatura deve ocorrer antes da promoção.")
            if kind == "train_agent":
                plan["status"] = "TREINAMENTO_REGISTRADO"
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("supervised_training_registered", plan_id=plan_id, agent=payload.get("agent"))
                return "✅ Sessão de treinamento registrada. Nenhum peso, função ou código foi alterado."
            if kind == "repair":
                plan["status"] = "DIAGNOSTICO_CONCLUÍDO"
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                return "✅ Diagnóstico confirmado e registrado. Nenhum reparo automático foi executado."
        # Ainda não há comandos oficiais validados para reiniciar serviços.
        return f"ℹ️ Confirmação recebida para `{action}`, mas a execução foi bloqueada: comando oficial não validado. Nenhuma alteração foi feita."

    async def handle(self, raw: str):
        kind, value = self.intent(raw)
        if kind == "exit":
            self.in_chat = False
            self.running = False
            return "👋 Supervisor encerrado."
        if kind == "chat":
            self.in_chat = True
            return "💬 Chat ativo. Digite sua pergunta ou SAIR."
        if self.dialogue == "create_agent" and kind == "model":
            self.dialogue = None
            objective = raw.strip()
            if not objective:
                return "Não recebi a tarefa do agente. Envie nome, objetivo e link do repositório em uma única mensagem, se houver."
            generated_name = f"agente-{int(time.time())}"
            return await self.administrative_plan("create_agent", f"{generated_name}: {objective}")
        if self.dialogue == "install_agent" and kind == "model":
            self.dialogue = None
            return await self.prepare_natural_install(raw.strip())
        if kind == "agent_builder":
            self.dialogue = "create_agent"
            return ("Sim. Posso preparar isso. Envie em uma única mensagem o objetivo do agente, o nome desejado e o link do repositório, se existir; "
                    "eu devolvo uma proposta consolidada para uma única aprovação.")
        if kind == "agent_installer":
            return await self.prepare_natural_install(value or "")
        if kind == "read_file":
            query = re.sub(r"^(abrir|abra|ler|leia|carregar|analise|analisar)\s+(o\s+)?arquivo\s*", "", value, flags=re.IGNORECASE).strip()
            matches = await asyncio.to_thread(find_aura_files, query)
            if not matches:
                return f"Não encontrei arquivo textual correspondente a: {query}. Verifique o nome dentro de {AURA_ROOT}."
            if len(matches) > 1 and matches[0].name.lower() != query.lower():
                choices = "\n".join(f"{index + 1}. {path}" for index, path in enumerate(matches))
                return f"Encontrei mais de um arquivo possível. Escolha pelo número em uma única resposta:\n{choices}"
            target = matches[0]
            try:
                content = await asyncio.to_thread(read_aura_file, target)
            except Exception as exc:
                return f"Não consegui ler {target.name}: {exc}"
            snapshot = await asyncio.to_thread(collect_snapshot)
            async with self.model_lock:
                return await ask_ollama(f"PEDIDO DO USUÁRIO: {value}\\nARQUIVO ENCONTRADO: {target}\\nCONTEÚDO:\\n{content}", snapshot)
        if kind == "full_spec":
            self.dialogue = None
            return await self.prepare_full_spec(value or "")
        if kind == "status":
            snapshot = await asyncio.to_thread(collect_snapshot)
            show_status(snapshot)
            return None
        if kind == "help":
            return self.help()
        if kind == "cancel":
            self.pending_action = None
            self.state.state["pending_action"] = None
            self.state.transition("CONFIRMATION_CANCELLED", to_state="IDLE")
            return "✅ Ação cancelada. Nada foi alterado."
        if kind in {"repair_plan", "create_agent", "edit_agent", "order_tasks", "install_skill", "install_repo", "train_agent"}:
            return await self.administrative_plan(kind, value or "")
        if kind == "action":
            if not self.lock_available:
                return "⚠️ Outra instância do Harness já está ativa. Esta sessão ficará somente para consulta."
            return self.ask_confirmation(value)
        if kind == "confirm":
            if self.pending_action and value == self.pending_action:
                action = self.pending_action
                self.pending_action = None
                return await self.execute(action)
            return "❌ Confirmação não corresponde a nenhuma ação pendente. Digite AJUDA."
        snapshot = await asyncio.to_thread(collect_snapshot)
        async with self.model_lock:
            return await ask_ollama(raw, snapshot)

    def _paste_available(self) -> bool:
        """Detecta se ainda há linhas do bloco colado no terminal."""
        if os.name == "nt":
            try:
                import msvcrt
                return bool(msvcrt.kbhit())
            except Exception:
                return False
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.12)
            return bool(ready)
        except (OSError, ValueError):
            return False

    async def _read_input_block(self, first_line: str) -> str:
        """Agrupa prompt Markdown colado para evitar uma chamada por linha."""
        first = first_line.rstrip("\r\n")
        normalized_first = normalize(first)
        is_markdown_block = (
            normalized_first.startswith("# role")
            or normalized_first.startswith("# objetivo")
            or normalized_first.startswith("# objective")
            or len(first) > 700
        )
        if not is_markdown_block:
            return first
        lines = [first]
        while self.running:
            await asyncio.sleep(0.16)
            if not self._paste_available():
                break
            next_line = await asyncio.to_thread(sys.stdin.readline)
            if not next_line:
                break
            lines.append(next_line.rstrip("\r\n"))
        return "\n".join(lines).strip()

    async def input_loop(self):
        while self.running:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            block = await self._read_input_block(line)
            if block:
                await self.queue.put(block)

    def _recompute_global_state(self) -> str:
        states = [self.state.state["components"].get(name, {}).get("state") for name in ("engine", "bridge", "voice")]
        if all(item == "READY" for item in states):
            return "STACK_RUNNING"
        if any(item in {"READY", "PORT_OPEN", "PROCESS_RUNNING", "DEGRADED"} for item in states):
            return "DEGRADED"
        if any(item in {"STARTING", "HEALTH_CHECKING"} for item in states):
            return "STARTING_STACK"
        return "IDLE"

    async def monitor_loop(self):
        """Observa saúde e recupera apenas processos pertencentes a esta sessão."""
        while self.running:
            try:
                for name in ("engine", "bridge", "voice"):
                    status = await asyncio.to_thread(self.services.status, name)
                    item = self.state.state["components"].setdefault(name, _component_record(name))
                    if status.get("healthy"):
                        if item.get("state") != "READY":
                            self.state.transition("HEALTH_OK", name, "READY", port=status.get("port"))
                        continue
                    if not item.get("owned_by_harness") or item.get("state") in {"UNKNOWN", "STOPPED", "BLOCKED"}:
                        continue
                    now = time.time()
                    recovery = self.state.state.setdefault("recovery", {"attempts": {}, "window_seconds": 300, "max_attempts": 3})
                    record = recovery.setdefault("attempts", {}).setdefault(name, {"count": 0, "window_started": now})
                    if now - float(record.get("window_started", now)) > recovery.get("window_seconds", 300):
                        record.update({"count": 0, "window_started": now})
                    if record["count"] >= recovery.get("max_attempts", 3):
                        self.state.transition("RECOVERY_LIMIT_REACHED", name, "FAILED", error="RECOVERY_LIMIT_REACHED")
                        continue
                    record["count"] += 1
                    self.state.transition("RECOVERY_REQUESTED", component=name, to_state="RECOVERING", attempt=record["count"])
                    await asyncio.to_thread(self.services.stop, name)
                    result = await asyncio.to_thread(self.services.start, name)
                    if result.get("ok"):
                        self.state.transition("RECOVERY_SUCCEEDED", name, "READY", pid=result.get("pid"), owned_by_harness=True)
                    else:
                        self.state.transition("HEALTH_FAILED", name, "DEGRADED", error=result.get("status") or result.get("error"))
                desired = self._recompute_global_state()
                if self.state.state.get("global_state") not in {"AWAITING_CONFIRMATION", "STARTING_STACK", "RECOVERING"} and desired != self.state.state.get("global_state"):
                    self.state.transition("OPERATION_COMPLETED", to_state=desired)
            except Exception as exc:
                audit("monitor_error", error=f"{type(exc).__name__}: {exc}")
            await asyncio.sleep(5)

    async def run(self):
        ensure_control_dirs()
        if not self.lock_available:
            title("⚠️ AURA Harness em modo consulta: outra instância possui o lock operacional.")
        monitor_task = asyncio.create_task(self.monitor_loop())
        title(f"🤖 Harness Supervisor Pro\nModelo: {MODEL} · Retenção: {KEEP_ALIVE} · Contexto: {NUM_CTX}\n🛡️ Paper trade ativo · Execução real bloqueada · Reparo controlado")
        input_task = asyncio.create_task(self.input_loop())
        try:
            while self.running:
                raw = await self.queue.get()
                if not raw:
                    continue
                result = await self.handle(raw)
                if result:
                    print_complete(result)
                if self.in_chat and self.running:
                    if RICH:
                        console.print("Você: ", end="")
                    else:
                        print("Você: ", end="", flush=True)
        finally:
            input_task.cancel()
            monitor_task.cancel()
            self.state.release()


def self_test() -> None:
    assert KEEP_ALIVE not in {"0", "0s", "0m"}
    assert os.environ.get("PAPER_TRADE") == "true"
    assert os.environ.get("EXECUTION_ALLOWED") == "false"
    assert repo_url("https://github.com/org/repo") == "https://github.com/org/repo"
    print("Harness self-test: OK; modo seguro ativo; nenhuma alteração executada.")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        raise SystemExit(0)
    try:
        asyncio.run(Halem().run())
    except KeyboardInterrupt:
        print("\n[INFO] Supervisor encerrado.")
