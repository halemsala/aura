from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import io
import json
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
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

# Config opcional via .env (arquivo texto simples ao lado do script). Só pode ajustar
# parâmetros operacionais (raiz do projeto, modelo, contexto, URL do Ollama etc.).
# Nunca é lido para as chaves de política de segurança acima: essas continuam fixas
# pelos os.environ.setdefault já executados, então um .env malicioso ou desatualizado
# não consegue destravar execução real.
_SAFE_ENV_OVERRIDABLE = {
    "AURA_ROOT", "AURA_OLLAMA_URL", "AURA_CHAT_MODEL", "AURA_KEEP_ALIVE",
    "AURA_NUM_CTX", "AURA_NUM_PREDICT", "AURA_EMOJI",
    "AURA_GITHUB_DISCOVERY", "AURA_MAX_ARCHIVE_BYTES", "AURA_GITHUB_CACHE_TTL",
}


def _load_env_file(path: Path) -> None:
    try:
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key not in _SAFE_ENV_OVERRIDABLE:
                continue
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    except OSError:
        pass


try:
    _load_env_file(Path(__file__).resolve().parent / ".env")
except NameError:
    pass  # __file__ pode faltar em alguns empacotamentos; .env vira opcional.

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
HISTORY_FILE = CONTROL_ROOT / "chat_history.json"
AGENTS_ROOT = AURA_ROOT / "agents"
SKILLS_ROOT = AURA_ROOT / "skills"
INSTALLED_REPOS_ROOT = AURA_ROOT / "instalado"
GITHUB_CACHE_TTL_SECONDS = int(os.environ.get("AURA_GITHUB_CACHE_TTL", "600"))
ALLOWED_REPO_HOSTS = {"github.com", "gitlab.com", "codeberg.org"}
READABLE_EXTENSIONS = {".txt", ".html", ".htm", ".json", ".csv", ".md", ".log"}
MAX_READ_BYTES = 5 * 1024 * 1024
MAX_MODEL_FILE_CHARS = 50000
MAX_ARCHIVE_BYTES = int(os.environ.get("AURA_MAX_ARCHIVE_BYTES", str(80 * 1024 * 1024)))
GITHUB_DISCOVERY = os.environ.get("AURA_GITHUB_DISCOVERY", "1") not in {"0", "false", "no"}
DEFAULT_BRANCHES = ("main", "master", "HEAD")

if KEEP_ALIVE in {"0", "0s", "0m"}:
    raise RuntimeError("AURA_KEEP_ALIVE não pode ser zero.")

SERVICES = {
    "ollama": ("127.0.0.1", 11434, "/api/tags"),
    "engine": ("127.0.0.1", 8765, "/api/health"),
    "bridge": ("127.0.0.1", 8080, "/health"),
    "voice": ("127.0.0.1", 8099, "/api/health"),
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
    "iniciar tudo": "Subir Engine (8765), Bridge (8080) e Voice (8099), e verificar/iniciar o Ollama (11434), "
                    "cada serviço somente por inicializador oficial já existente no projeto; nenhum comando novo é inventado.",
    "iniciar engine": "Iniciar o servidor Engine local na porta 8765.",
    "iniciar bridge": "Iniciar o Bridge local na porta 8080.",
    "iniciar voice": "Iniciar o servidor Voice local na porta 8099.",
    "reiniciar engine": "Reiniciar o servidor Engine local.",
    "reiniciar bridge": "Reiniciar o Bridge local.",
    "reiniciar voice": "Reiniciar o servidor Voice local.",
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


_GITHUB_SEARCH_CACHE: dict[str, tuple[float, list[dict]]] = {}


def search_github_repos(query: str, max_results: int = 4) -> list[dict]:
    """Busca somente leitura na API pública do GitHub (sem token, sem chave armazenada).
    Usada para fundamentar as sugestões de skills/repositórios em candidatos reais, nunca
    para instalar nada. Falha silenciosamente (lista vazia) se offline, sem rede liberada
    ou se o limite de requisições anônimo (rate limit) for atingido. Resultado é cacheado
    em memória por AURA_GITHUB_CACHE_TTL segundos para não repetir a mesma busca toda hora
    e evitar bater no rate limit anônimo do GitHub."""
    if not GITHUB_DISCOVERY:
        return []
    cache_key = f"{query}:{max_results}"
    cached = _GITHUB_SEARCH_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < GITHUB_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc", "per_page": max_results})
        request = urllib.request.Request(
            f"https://api.github.com/search/repositories?{params}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "AURA-Harness/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=4.0) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        results = []
        for item in data.get("items", [])[:max_results]:
            results.append({
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "stars": item.get("stargazers_count"),
                "description": (item.get("description") or "")[:200],
                "updated_at": item.get("updated_at"),
            })
        _GITHUB_SEARCH_CACHE[cache_key] = (time.time(), results)
        return results
    except Exception:
        return cached[1] if cached else []


RUNNABLE_SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".py", ".sh"}


def find_existing(paths: list[Path]) -> Path | None:
    """Retorna o primeiro caminho oficial (já esperado pelo projeto) que existir de fato no disco."""
    for candidate in paths:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def find_in_dir_by_hint(directory: Path, hints: tuple[str, ...]) -> Path | None:
    """Procura, dentro de um diretório oficial já citado no projeto (ex.: scripts/bridge),
    um único script executável cujo nome bata com os indícios dados. Nunca inventa nome:
    se não houver diretório, nenhum arquivo compatível, ou mais de um candidato ambíguo,
    retorna None para que o chamador reporte erro claro em vez de arriscar o script errado."""
    try:
        if not directory.is_dir():
            return None
    except OSError:
        return None
    candidates = []
    for entry in directory.iterdir():
        try:
            if not entry.is_file() or entry.suffix.lower() not in RUNNABLE_SCRIPT_SUFFIXES:
                continue
        except OSError:
            continue
        name = _normalized_filename(entry.name)
        if any(hint in name for hint in hints):
            candidates.append(entry)
    if len(candidates) == 1:
        return candidates[0]
    return None


def run_official_script(path: Path, timeout: int = 45) -> subprocess.CompletedProcess:
    """Executa apenas scripts já existentes no projeto (nunca uma linha de comando construída na hora)."""
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    elif suffix in {".bat", ".cmd"}:
        command = ["cmd", "/c", str(path)]
    elif suffix == ".py":
        command = [sys.executable, str(path)]
    elif suffix == ".sh":
        command = ["bash", str(path)]
    else:
        raise ValueError(f"extensão de script não suportada para execução: {suffix}")
    return subprocess.run(command, cwd=str(path.parent), capture_output=True, text=True, timeout=timeout)


def resolve_master_starter() -> Path | None:
    """Inicializador 'sobe tudo' já esperado pelo projeto (citado no monitor .ps1)."""
    return find_existing([
        AURA_ROOT / "INSTALAR_E_INICIAR_TUDO.bat",
        AURA_ROOT / "RECUPERAR_AURA_SERVICOS.ps1",
        AURA_ROOT / "RECUPERAR_AURA_SERVICOS.bat",
    ])


def resolve_voice_starter() -> Path | None:
    """Inicializador do Voice já citado no monitor .ps1 (linha do bloco iniciar_voz)."""
    return find_existing([AURA_ROOT / "iniciar_voz.bat", AURA_ROOT / "iniciar_voz.sh"])


def resolve_bridge_starter() -> Path | None:
    """Procura um inicializador oficial dentro de C:\\aura\\scripts\\bridge, sem inventar nome de arquivo."""
    return find_in_dir_by_hint(AURA_ROOT / "scripts" / "bridge", ("start", "iniciar", "bridge", "run", "up"))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_read_error": str(exc), "path": str(path)}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_control_dirs() -> None:
    for path in (CONTROL_ROOT, STAGING_ROOT, BACKUP_ROOT, AGENTS_ROOT, SKILLS_ROOT, INSTALLED_REPOS_ROOT):
        path.mkdir(parents=True, exist_ok=True)


AUDIT_ROTATE_BYTES = 10 * 1024 * 1024


def _rotate_audit_log_if_needed() -> None:
    """Evita crescimento ilimitado do audit.jsonl: ao passar do limite, move para
    audit.jsonl.1 (sobrescrevendo o anterior) e começa um arquivo novo. Nunca apaga
    o histórico mais recente, só empurra o mais antigo para o arquivo .1."""
    try:
        if AUDIT_LOG.is_file() and AUDIT_LOG.stat().st_size > AUDIT_ROTATE_BYTES:
            rotated = AUDIT_LOG.with_suffix(AUDIT_LOG.suffix + ".1")
            shutil.copy2(AUDIT_LOG, rotated)
            AUDIT_LOG.write_text("", encoding="utf-8")
    except OSError:
        pass  # rotação é best-effort; nunca deve impedir o registro do evento atual.


def audit(event: str, **details) -> None:
    ensure_control_dirs()
    _rotate_audit_log_if_needed()
    record = {"timestamp": utc_now(), "event": event, **details}
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_name(value: str) -> str:
    value = normalize(value).replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,48}", value):
        raise ValueError("nome inválido; use 2–49 caracteres alfanuméricos, hífen ou sublinhado")
    return value


def load_plans() -> list[dict]:
    data = read_json(PLANS_FILE)
    return data if isinstance(data, list) else []


def load_chat_history() -> list[tuple[str, str]]:
    """Recupera o histórico curto de chat salvo entre reinícios. Somente o que o próprio
    usuário digitou/recebeu nesta sessão local — nada além disso é persistido aqui."""
    data = read_json(HISTORY_FILE)
    if not isinstance(data, list):
        return []
    return [(item[0], item[1]) for item in data if isinstance(item, list) and len(item) == 2]


def save_chat_history(history: list[tuple[str, str]]) -> None:
    try:
        ensure_control_dirs()
        HISTORY_FILE.write_text(json.dumps(history[-12:], ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # persistência de histórico é best-effort; nunca deve travar a conversa.


def list_staging() -> list[dict]:
    """Inventário somente leitura do que está em STAGING_ROOT aguardando revisão/promoção."""
    items: list[dict] = []
    try:
        if not STAGING_ROOT.is_dir():
            return items
        for entry in sorted(STAGING_ROOT.iterdir()):
            manifest_path = entry / "_staging_origin.json"
            if not entry.is_dir() or not manifest_path.is_file():
                continue
            data = read_json(manifest_path)
            if isinstance(data, dict):
                items.append({"path": str(entry), **data})
    except OSError:
        pass
    return items


def find_staged_by_label(needle: str) -> Path | None:
    """Localiza uma pasta em staging pelo nome (ou prefixo do nome, sem o timestamp)."""
    needle_norm = normalize(needle)
    candidates = []
    try:
        for entry in STAGING_ROOT.iterdir():
            if not entry.is_dir():
                continue
            if normalize(entry.name).startswith(needle_norm) or needle_norm in normalize(entry.name):
                candidates.append(entry)
    except OSError:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return None


def promote_staged_item(staged_dir: Path) -> tuple[Path, Path | None]:
    """Copia (nunca move, nunca executa) o conteúdo revisado de staging para a área ativa
    (SKILLS_ROOT para 'install_skill', INSTALLED_REPOS_ROOT para 'install_repo'), faz backup
    do destino se já existir, e marca o manifesto como promovido. Exige que o chamador já
    tenha passado pelo fluxo de plano + CONFIRMAR — esta função em si não pede confirmação."""
    manifest_path = staged_dir / "_staging_origin.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("manifesto de origem ausente ou inválido; não é possível promover com segurança")
    kind = manifest.get("kind", "install_repo")
    label = safe_name(manifest.get("label") or staged_dir.name.rsplit("-", 1)[0])
    dest_root = SKILLS_ROOT if kind == "install_skill" else INSTALLED_REPOS_ROOT
    destination = (dest_root / label).resolve()
    if dest_root.resolve() not in destination.parents and destination != dest_root.resolve():
        raise ValueError("destino de promoção fora da área permitida")
    backup = None
    if destination.exists():
        backup = BACKUP_ROOT / f"{label}-{int(time.time())}"
        shutil.copytree(destination, backup)
        shutil.rmtree(destination)
    shutil.copytree(staged_dir, destination)
    manifest["promoted"] = True
    manifest["promoted_at"] = utc_now()
    (destination / "_staging_origin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (staged_dir / "_staging_origin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination, backup


def list_local_skills() -> list[dict]:
    """Inventário somente leitura do que já existe em SKILLS_ROOT. Nunca cria, baixa ou apaga nada."""
    items: list[dict] = []
    try:
        if not SKILLS_ROOT.is_dir():
            return items
        for entry in sorted(SKILLS_ROOT.iterdir()):
            try:
                info: dict = {"name": entry.name, "type": "dir" if entry.is_dir() else "file"}
                manifest = entry / "manifest.json" if entry.is_dir() else None
                if manifest and manifest.is_file():
                    data = read_json(manifest)
                    if isinstance(data, dict) and data.get("description"):
                        info["description"] = str(data["description"])[:200]
            except OSError:
                continue
            items.append(info)
    except OSError:
        pass
    return items


async def ask_ollama_skill_suggestions(snapshot: dict, local_skills: list[dict], real_candidates: list[dict] | None = None) -> str:
    """Pede ao modelo ideias de skills/ferramentas para tornar a AURA mais capaz.
    Não instala nada, não afirma ter acessado a internet, e sempre remete de volta
    ao fluxo existente de aprovação (`instalar skill <url>` + CONFIRMAR). Quando
    `real_candidates` vem preenchido (busca real no GitHub feita por search_github_repos),
    o modelo é instruído a priorizar e comentar esses repositórios reais em vez de inventar
    nomes — reduz alucinação e torna a sugestão de fato acionável."""
    system = (
        "Você é o consultor de capacidades do Harness AURA. Sua única tarefa agora é sugerir, em português, "
        "até 5 skills ou ferramentas que poderiam tornar o sistema mais útil, com base apenas no contexto "
        "técnico fornecido (serviços ativos, skills já presentes, política de segurança, e candidatos reais "
        "de repositório, se houver). Para cada sugestão dê: nome curto, por que ajudaria, e o quão confiante "
        "você está. Se a lista de candidatos reais não estiver vazia, priorize comentar sobre eles (com a URL "
        "fornecida) em vez de inventar outros nomes; só sugira nomes fora da lista se for algo genérico e "
        "conhecido, deixando claro que não foi verificado agora. "
        "Nunca afirme ter instalado, baixado, testado ou acessado algo que não esteja no contexto fornecido. "
        "Nunca diga que uma skill já existe se ela não estiver na lista de skills existentes. "
        "Se o contexto for insuficiente para uma sugestão específica, diga isso em vez de inventar. "
        "Termine sempre lembrando que qualquer instalação real exige o comando 'instalar skill <url>' seguido "
        "de confirmação explícita do usuário; nada é instalado automaticamente por esta consulta."
    )
    context = {
        "servicos": snapshot.get("services", {}),
        "policy": snapshot.get("policy", {}),
        "skills_existentes": local_skills,
        "candidatos_reais_github": real_candidates or [],
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"CONTEXTO:\n{json.dumps(context, ensure_ascii=False)[:8000]}\n\nSugira melhorias."},
        ],
        "stream": True,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_gpu": 99, "num_ctx": NUM_CTX, "num_predict": 1024, "temperature": 0.3},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks: list[str] = []
    try:
        response = await asyncio.to_thread(urllib.request.urlopen, request, timeout=60)
        try:
            while True:
                line = await asyncio.to_thread(response.readline)
                if not line:
                    break
                part = json.loads(line.decode("utf-8", errors="replace"))
                text = part.get("message", {}).get("content", "")
                if text:
                    chunks.append(text)
                if part.get("done"):
                    break
        finally:
            response.close()
    except Exception as exc:
        return f"⚠️ Não foi possível consultar o modelo para sugestões agora (Ollama indisponível?): {exc}"
    return "".join(chunks).strip() or "Nenhuma sugestão retornada pelo modelo."


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


def parse_repo_ref(raw: str) -> tuple[str, str | None]:
    """Aceita opcionalmente uma ramificação explícita no formato 'URL@branch'
    (ex.: instalar repositorio https://github.com/org/repo@develop). Sem @branch,
    o download tenta os padrões (main, master) como já fazia antes."""
    raw = raw.strip()
    if "@" in raw:
        url_part, _, branch_part = raw.rpartition("@")
        branch_part = branch_part.strip()
        if url_part and branch_part and re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", branch_part):
            return repo_url(url_part), branch_part
    return repo_url(raw), None


def _archive_candidate_urls(url: str, branch: str | None = None) -> list[str]:
    """Monta URLs de tarball oficiais (sem shell, sem `git`) para os hosts permitidos.
    Só usa hosts de download-de-arquivo estático das próprias plataformas (codeload,
    gitlab archive, codeberg archive) — nunca um host arbitrário fora de ALLOWED_REPO_HOSTS.
    Se `branch` for informada, ela é tentada primeiro; senão usa os padrões (main, master)."""
    parsed = urllib.parse.urlparse(url)
    parts = [segment for segment in parsed.path.split("/") if segment]
    if len(parts) < 2:
        raise ValueError("URL de repositório precisa conter owner/repo")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    host = parsed.hostname
    branches = ([branch] + list(DEFAULT_BRANCHES[:2])) if branch else list(DEFAULT_BRANCHES[:2])
    candidates = []
    if host == "github.com":
        for b in branches:
            candidates.append(f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{b}")
    elif host == "gitlab.com":
        for b in branches:
            candidates.append(f"https://gitlab.com/{owner}/{repo}/-/archive/{b}/{repo}-{b}.tar.gz")
    elif host == "codeberg.org":
        for b in branches:
            candidates.append(f"https://codeberg.org/{owner}/{repo}/archive/{b}.tar.gz")
    else:
        raise ValueError("host não suportado para download de arquivo")
    return candidates


def _safe_extract_tar(archive_path: Path, dest_dir: Path) -> None:
    """Extrai um .tar.gz validando cada membro: recusa symlink/hardlink/device e qualquer
    caminho que tente escapar de dest_dir. Nunca executa nada dentro do arquivo."""
    dest_root = dest_dir.resolve()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"membro não seguro recusado: {member.name}")
            target = (dest_root / member.name).resolve()
            if dest_root != target and dest_root not in target.parents:
                raise ValueError(f"caminho fora da área de staging recusado: {member.name}")
        archive.extractall(dest_root)  # seguro aqui: já validamos todos os membros acima.


def _find_existing_staged(url: str) -> dict | None:
    """Evita baixar de novo o mesmo repositório: procura um manifesto _staging_origin.json
    já existente com a mesma source_url em STAGING_ROOT. Somente leitura."""
    try:
        if not STAGING_ROOT.is_dir():
            return None
        for entry in STAGING_ROOT.iterdir():
            manifest_path = entry / "_staging_origin.json"
            if not manifest_path.is_file():
                continue
            data = read_json(manifest_path)
            if isinstance(data, dict) and data.get("source_url") == url:
                return {"path": str(entry), **data}
    except OSError:
        pass
    return None


def download_repo_archive(url: str, label: str, kind: str = "install_repo", branch: str | None = None) -> dict:
    """Baixa (somente arquivo estático, sem `git clone`, sem executar nada) um repositório
    aprovado para STAGING_ROOT, calcula o checksum e escreve um manifesto de origem.
    Nunca roda setup.py, Makefile, instaladores ou scripts do pacote baixado — isso
    continua exigindo promoção manual e revisão humana, como já era a política do projeto.
    Se a mesma URL já estiver em staging, reaproveita o download em vez de duplicar."""
    existing = _find_existing_staged(url)
    if existing and not branch:
        return {**existing, "reused_existing": True}

    candidates = _archive_candidate_urls(url, branch)
    last_error: Exception | None = None
    for archive_url in candidates:
        try:
            request = urllib.request.Request(archive_url, headers={"User-Agent": "AURA-Harness/1.0"}, method="GET")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
                tmp_path = Path(tmp.name)
                with urllib.request.urlopen(request, timeout=20) as response:
                    total = 0
                    hasher = hashlib.sha256()
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise ValueError(f"arquivo excede o limite de {MAX_ARCHIVE_BYTES} bytes; abortado")
                        hasher.update(chunk)
                        tmp.write(chunk)
            dest_dir = STAGING_ROOT / f"{label}-{int(time.time())}"
            dest_dir.mkdir(parents=True, exist_ok=False)
            try:
                _safe_extract_tar(tmp_path, dest_dir)
            finally:
                tmp_path.unlink(missing_ok=True)
            manifest = {
                "source_url": url,
                "archive_url": archive_url,
                "kind": kind,
                "label": label,
                "sha256": hasher.hexdigest(),
                "downloaded_at": utc_now(),
                "promoted": False,
                "installers_executed": False,
            }
            (dest_dir / "_staging_origin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"path": str(dest_dir), **manifest}
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"não foi possível baixar nenhuma ramificação padrão: {last_error}")


RISK_PATTERNS = [
    (re.compile(rb"curl\s+[^\n|]{0,200}\|\s*(ba)?sh", re.IGNORECASE), "pipe curl -> shell"),
    (re.compile(rb"wget\s+[^\n|]{0,200}\|\s*(ba)?sh", re.IGNORECASE), "pipe wget -> shell"),
    (re.compile(rb"powershell[^\n]{0,80}-enc", re.IGNORECASE), "powershell com payload codificado"),
    (re.compile(rb"Invoke-Expression", re.IGNORECASE), "Invoke-Expression (PowerShell)"),
    (re.compile(rb"base64\s+-d[^\n]{0,120}\|\s*(ba)?sh", re.IGNORECASE), "base64 decodificado direto para shell"),
    (re.compile(rb"rm\s+-rf\s+/(?!\S)"), "rm -rf / (destrutivo)"),
    (re.compile(rb"eval\(\s*(base64|atob|exec)"), "eval() de conteúdo ofuscado"),
    (re.compile(rb"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "chave privada embutida no repositório"),
]
RISK_SCAN_EXTENSIONS = {".py", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".js", ".ts", ".yml", ".yaml", ".json", ".txt", ".md"}
RISK_SCAN_MAX_FILES = 400
RISK_SCAN_MAX_FILE_BYTES = 2 * 1024 * 1024


def scan_staged_for_risks(staged_dir: Path) -> list[str]:
    """Varredura estática, só leitura, por padrões clássicos de instalador malicioso ou
    segredo vazado (pipe-para-shell, PowerShell ofuscado, chave privada etc.). Isso é um
    ALERTA para revisão humana antes de promover — nunca bloqueia nem apaga nada sozinho,
    e nunca é 100% exaustivo (não substitui revisão manual real)."""
    findings: list[str] = []
    checked = 0
    try:
        for path in staged_dir.rglob("*"):
            if checked >= RISK_SCAN_MAX_FILES:
                findings.append(f"… varredura interrompida em {RISK_SCAN_MAX_FILES} arquivos (repositório grande; revise manualmente).")
                break
            try:
                if not path.is_file() or path.suffix.lower() not in RISK_SCAN_EXTENSIONS:
                    continue
                if path.stat().st_size > RISK_SCAN_MAX_FILE_BYTES:
                    continue
                checked += 1
                data = path.read_bytes()
            except OSError:
                continue
            for pattern, label in RISK_PATTERNS:
                if pattern.search(data):
                    findings.append(f"{path.relative_to(staged_dir)}: {label}")
    except OSError:
        pass
    return findings


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


def _check_one_service(name: str, host: str, port: int, health_path: str) -> tuple[str, dict]:
    online = tcp_check(host, port)
    item = {"online": online, "port": port}
    if online:
        item["health"] = http_json(f"http://{host}:{port}{health_path}")
    return name, item


def collect_snapshot():
    services = {}
    # Checa os serviços em paralelo (antes era sequencial): a latência total passa a ser
    # a do serviço mais lento, não a soma de todos, sem mudar o formato do snapshot.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(SERVICES), 1)) as pool:
        futures = [pool.submit(_check_one_service, name, host, port, health_path)
                   for name, (host, port, health_path) in SERVICES.items()]
        for future in concurrent.futures.as_completed(futures):
            name, item = future.result()
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
    return "\n".join(lines) + f"\nBOOT_RUNNING: {boot_state}\nPOLICY: paper_trade=true; execution_allowed=false; repair=disabled"


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


async def ask_ollama(user_text: str, snapshot: dict, history: list[tuple[str, str]] | None = None) -> str:
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
    messages = [{"role": "system", "content": system}]
    for user_turn, assistant_turn in (history or [])[-6:]:
        messages.append({"role": "user", "content": user_turn})
        messages.append({"role": "assistant", "content": assistant_turn})
    messages.append({"role": "user", "content": f"CONTEXTO:\n{compact_context(snapshot)}\n\nPEDIDO:\n{user_text}"})
    payload = {
        "model": MODEL,
        "messages": messages,
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
    attempts = 2  # 1 retentativa: o primeiro request após ociosidade pode falhar
    # enquanto o Ollama ainda está carregando o modelo residente na memória.
    last_error: Exception | None = None
    for attempt in range(attempts):
        chunks = []
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
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(1.5)
    if last_error is not None:
        return f"❌ Falha no Ollama (após retentativa): {last_error}. Verifique se o serviço está rodando em {OLLAMA_URL}."
    result = "".join(chunks).strip() or "NÃO CONFIRMADO"
    elapsed = time.perf_counter() - started
    return f"{result}\n\n[dim]⏱ {elapsed:.1f}s · chamada única · modelo residente[/dim]" if RICH else f"{result}\n[tempo: {elapsed:.1f}s]"


class Halem:
    def __init__(self):
        self.running = True
        self.in_chat = False
        self.pending_action: str | None = None
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.model_lock = asyncio.Lock()
        self.dialogue: str | None = None
        self.clarification_used = False
        # Memória curta só da conversa livre (fallback para o modelo), não das ações
        # determinísticas. Mantém continuidade em "chat" sem crescer sem limite.
        self.history: list[tuple[str, str]] = []
        self.max_history_turns = 6

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
        if any(phrase in text for phrase in (
            "descobrir skills", "buscar skills", "novas skills", "sugerir skills",
            "quais skills existem", "que skills existem", "novas ferramentas",
            "sugerir ferramentas", "melhorar o sistema", "otimizar a aura",
            "integrar novas ferramentas", "integrar novas skills", "ficar mais inteligente",
        )):
            return "discover_skills", None
        if text in {"listar staging", "ver staging", "staging", "listar pendentes"}:
            return "list_staging", None
        if text.startswith("promover "):
            return "promote_staged", text.removeprefix("promover ").strip()
        if text in {"reparar", "diagnosticar reparo", "plano de reparo"}:
            return "repair_plan", None
        if text.startswith("criar agente "):
            return "create_agent", text.removeprefix("criar agente ").strip()
        if text.startswith("editar agente "):
            return "edit_agent", text.removeprefix("editar agente ").strip()
        if text.startswith("ordenar tarefas "):
            return "order_tasks", text.removeprefix("ordenar tarefas ").strip()
        if text.startswith("instalar skill "):
            m = re.match(r"instalar\s+skill\s+(.+)", raw.strip(), re.IGNORECASE)
            return "install_skill", (m.group(1).strip() if m else text.removeprefix("instalar skill ").strip())
        if text.startswith("instalar repositorio "):
            m = re.match(r"instalar\s+reposit[oó]rio\s+(.+)", raw.strip(), re.IGNORECASE)
            return "install_repo", (m.group(1).strip() if m else text.removeprefix("instalar repositorio ").strip())
        if text.startswith("treinar agente "):
            return "train_agent", text.removeprefix("treinar agente ").strip()

        # --- Fallback tolerante para frases naturais que não usam o comando exato ---
        # Mesmo caminho de saída (ainda passa por administrative_plan -> ask_plan ->
        # exige CONFIRMAR); isto so amplia o RECONHECIMENTO, nao reduz nenhuma trava.
        m = re.search(
            r"\b(?:criar?|constr[uó]a?|cri[ae])\s+(?:um\s+|o\s+)?agente\s+(?:chamado\s+)?"
            r"([a-z0-9_-]+)(?:\s+pra)?\s*[:\u2013]\s*(.+)",
            text,
        )
        if m:
            return "create_agent", f"{m.group(1).strip()}: {m.group(2).strip()}"

        m = re.search(
            r"\b(?:editar?|mud[ae]|altera[r]?|atualiza[r]?)\s+(?:o\s+)?agente\s+"
            r"([a-z0-9_-]+)(?:\s+pra)?\s*[:\u2013]\s*(.+)",
            text,
        )
        if m:
            return "edit_agent", f"{m.group(1).strip()}: {m.group(2).strip()}"

        m = re.search(
            r"\b(?:ordena[r]?|organiza[r]?|reordena[r]?)\s+(?:as\s+)?tarefas\s+(?:do\s+agente\s+)?"
            r"([a-z0-9_-]+)(?:\s+pra)?\s*[:\u2013]\s*(.+)",
            text,
        )
        if m:
            return "order_tasks", f"{m.group(1).strip()}: {m.group(2).strip()}"

        m = re.search(r"\b(?:instala[r]?)\s+(?:a\s+)?skill\s+(https?://\S+)", raw, re.IGNORECASE)
        if m:
            return "install_skill", m.group(1).strip()

        m = re.search(r"\b(?:instala[r]?)\s+(?:o\s+)?reposit[oó]rio\s+(https?://\S+)", raw, re.IGNORECASE)
        if m:
            return "install_repo", m.group(1).strip()

        m = re.search(r"\b(?:treina[r]?)\s+(?:o\s+)?agente\s+([a-z0-9_-]+)", text)
        if m:
            return "train_agent", m.group(1).strip()
        if text in {"cancelar", "cancela", "nao", "não"}:
            return "cancel", None
        if text.startswith("confirmar "):
            return "confirm", text.removeprefix("confirmar ").strip()

        # Compreende pedidos naturais de inicialização antes de chamar o modelo.
        if any(phrase in text for phrase in (
            "iniciar tudo", "inicie tudo", "iniciar tudo de uma vez", "subir tudo", "suba tudo",
            "levantar tudo", "levante tudo", "levanta tudo", "subir todos os servicos", "subir todos os serviços",
            "iniciar todos os servicos", "iniciar todos os serviços", "ligar todos os servicos",
            "ligar todos os serviços", "start all", "sobe tudo", "sobe engine bridge e voice",
        )):
            return "action", "iniciar tudo"
        if any(phrase in text for phrase in ("inicie o aura", "iniciar o aura", "ligue o aura", "ligar o aura", "inicie aura", "ligue os servicos", "iniciar os servicos")):
            return "action", "ativar segura"
        for service in ("engine", "bridge", "voice"):
            # Checa "reiniciar"/"restart" ANTES de "iniciar": "reiniciar bridge" contém
            # literalmente a substring "iniciar bridge", então a ordem inversa faria
            # um pedido de reinício cair sempre no caminho de início simples.
            if any(phrase in text for phrase in (f"reiniciar {service}", f"restart {service}")):
                return "action", f"reiniciar {service}"
            if any(phrase in text for phrase in (f"iniciar {service}", f"ligar {service}", f"ative {service}")):
                return "action", f"iniciar {service}"
        if text == "ativar segura":
            return "action", text
        return "model", None

    def help(self):
        return (                "Comandos: status · chat · ajuda · reparar · criar agente NOME: OBJETIVO · "
                "editar agente NOME: CAMPO=VALOR · ordenar tarefas NOME: T1 > T2 · "
                "instalar skill URL[@branch] · instalar repositorio URL[@branch] · listar staging · "
                "promover NOME · treinar agente NOME · "
                "inicie o aura · iniciar tudo · ativar segura · descobrir skills · cancelar · sair\n"
                "Operações administrativas geram plano, ficam em staging e exigem confirmação exata. "
                "Código externo nunca é executado automaticamente; `promover` também exige confirmação própria.")

    def ask_plan(self, kind: str, title_text: str, payload: dict):
        try:
            plan_id = save_plan(kind, title_text, payload)
        except ValueError as exc:
            return f"❌ Plano rejeitado: {exc}"
        self.pending_action = f"plano {plan_id}"
        return (f"⚠️ PLANO PENDENTE {plan_id}\n{title_text}\n"
                f"Payload: {json.dumps(payload, ensure_ascii=False)}\n\n"
                f"Nada foi alterado. Digite exatamente: CONFIRMAR {self.pending_action.upper()}\n"
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
                url, branch = parse_repo_ref(value)
            except ValueError as exc:
                return f"❌ Origem rejeitada: {exc}"
            title_text = f"Baixar para staging para revisão manual (branch: {branch})" if branch else "Baixar para staging para revisão manual"
            return self.ask_plan("install_repo", title_text, {"url": url, "branch": branch, "execute_installers": False})
        if kind == "install_skill":
            try:
                url, branch = parse_repo_ref(value)
            except ValueError as exc:
                return f"❌ Origem rejeitada: {exc}"
            title_text = f"Baixar skill para staging para revisão manual (branch: {branch})" if branch else "Baixar skill para staging para revisão manual"
            return self.ask_plan("install_skill", title_text, {"url": url, "branch": branch, "execute_installers": False})
        if kind == "promote_staged":
            if not value:
                return "Formato: promover NOME (use o nome mostrado em `listar staging`)."
            staged_dir = await asyncio.to_thread(find_staged_by_label, value)
            if not staged_dir:
                return f"❌ Não encontrei um único item em staging correspondente a '{value}'. Use `listar staging` para ver os nomes exatos."
            risks = await asyncio.to_thread(scan_staged_for_risks, staged_dir)
            risk_note = ("\n⚠️ ALERTAS da varredura estática (revise antes de confirmar):\n" + "\n".join(f"  • {r}" for r in risks)) if risks else "\nVarredura estática: nenhum padrão suspeito encontrado (não substitui revisão manual)."
            return self.ask_plan("promote_staged", f"Promover '{staged_dir.name}' de staging para a área ativa{risk_note}", {"staged_dir": str(staged_dir)})
        if kind == "train_agent":
            name = safe_name(value)
            return self.ask_plan("train_agent", "Registrar treinamento supervisionado", {"agent": name, "mode": "supervised", "change_weights": False})
        return "❌ Operação administrativa desconhecida."

    def ask_confirmation(self, action: str):
        self.pending_action = action
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

    async def show_staging(self) -> str:
        """Lista (somente leitura) tudo que está em STAGING_ROOT aguardando revisão/promoção."""
        items = await asyncio.to_thread(list_staging)
        if not items:
            return f"📭 Nada em staging no momento ({STAGING_ROOT})."
        lines = [f"📦 Itens em staging ({len(items)}):"]
        for item in items:
            status = "✅ promovido" if item.get("promoted") else "⏳ aguardando revisão"
            name = Path(item["path"]).name
            lines.append(f"  • {name} — origem: {item.get('source_url', '?')} — {status}")
        lines.append("\nPara promover: `promover NOME` (roda varredura estática e pede confirmação antes de mover para a área ativa).")
        return "\n".join(lines)

    async def discover_skills(self) -> str:
        """Consulta somente leitura: lista skills já presentes + pede sugestões ao modelo
        para tornar a AURA mais capaz. Nunca instala, baixa ou executa nada por si só."""
        local_skills = await asyncio.to_thread(list_local_skills)
        snapshot = await asyncio.to_thread(collect_snapshot)

        real_candidates: list[dict] = []
        if GITHUB_DISCOVERY:
            # Buscas fixas e amplas relacionadas ao domínio da AURA (agentes locais, modelos
            # via Ollama, MCP). Somente leitura via API pública do GitHub; sem token salvo.
            queries = ["ollama agent tool skill", "mcp server tool", "local llm agent supervisor"]
            searches = await asyncio.gather(*(asyncio.to_thread(search_github_repos, q, 3) for q in queries))
            seen_urls = set()
            for batch in searches:
                for item in batch:
                    if item["url"] not in seen_urls:
                        seen_urls.add(item["url"])
                        real_candidates.append(item)

        suggestions = await ask_ollama_skill_suggestions(snapshot, local_skills, real_candidates)

        lines = ["🧭 DESCOBERTA DE SKILLS (somente leitura — nada é instalado aqui)\n"]
        if local_skills:
            lines.append(f"📦 Skills já presentes em {SKILLS_ROOT} ({len(local_skills)}):")
            for item in local_skills:
                desc = f" — {item['description']}" if item.get("description") else ""
                lines.append(f"  • {item['name']}{desc}")
        else:
            lines.append(f"📦 Nenhuma skill instalada/staged encontrada em {SKILLS_ROOT}.")
        if real_candidates:
            lines.append(f"\n🔎 Candidatos reais encontrados agora no GitHub ({len(real_candidates)}):")
            for item in real_candidates:
                lines.append(f"  • {item['name']} ({item['stars']}★) — {item['url']}")
        elif GITHUB_DISCOVERY:
            lines.append("\n🔎 Busca no GitHub não retornou candidatos agora (offline, sem rede liberada ou rate limit).")
        lines.append("\n💡 Sugestões do modelo para tornar a AURA mais capaz:")
        lines.append(suggestions)
        lines.append("\nPara instalar de verdade: `instalar skill <url>` (baixa para staging como arquivo estático, "
                      "sem `git clone` e sem executar nada, após CONFIRMAR; promoção continua manual).")
        audit("skills_discovery_run", local_skills_count=len(local_skills), real_candidates_count=len(real_candidates))
        return "\n".join(lines)

    async def run_start_all(self) -> str:
        """'iniciar tudo': sobe Engine/Bridge/Voice e verifica/inicia Ollama, usando somente
        inicializadores oficiais já existentes no projeto. Nunca inventa comando de start; se
        um serviço não tiver inicializador oficial localizado, reporta erro claro para aquele
        serviço em vez de tentar um substituto."""
        report = ["🚀 INICIAR TUDO — usando apenas inicializadores oficiais já existentes no projeto:\n"]
        used_scripts: dict[str, str | None] = {"master": None, "voice": None, "bridge": None}

        master = await asyncio.to_thread(resolve_master_starter)
        if master:
            used_scripts["master"] = master.name
            try:
                result = await asyncio.to_thread(run_official_script, master, 60)
                report.append(f"• Inicializador mestre `{master.name}`: código de saída={result.returncode}")
                tail = (result.stdout or "").strip()[-500:]
                if tail:
                    report.append(f"  saída: {tail}")
                if result.returncode != 0:
                    err_tail = (result.stderr or "").strip()[-500:]
                    if err_tail:
                        report.append(f"  erro: {err_tail}")
            except Exception as exc:
                report.append(f"• Inicializador mestre `{master.name}` falhou ao executar: {exc}")
            await asyncio.sleep(3)
        else:
            report.append("• Nenhum inicializador mestre oficial encontrado "
                           "(esperava INSTALAR_E_INICIAR_TUDO.bat, RECUPERAR_AURA_SERVICOS.ps1 ou .bat em "
                           f"{AURA_ROOT}). Tentando inicializadores oficiais por serviço.")

            voice_script = await asyncio.to_thread(resolve_voice_starter)
            if voice_script:
                used_scripts["voice"] = voice_script.name
                try:
                    result = await asyncio.to_thread(run_official_script, voice_script, 30)
                    report.append(f"• Voice via `{voice_script.name}`: código de saída={result.returncode}")
                except Exception as exc:
                    report.append(f"• Voice via `{voice_script.name}` falhou ao executar: {exc}")
            else:
                report.append("• Voice: ❌ nenhum inicializador oficial encontrado "
                               f"(esperava iniciar_voz.bat/.sh em {AURA_ROOT}). Serviço não iniciado.")

            bridge_script = await asyncio.to_thread(resolve_bridge_starter)
            if bridge_script:
                used_scripts["bridge"] = bridge_script.name
                try:
                    result = await asyncio.to_thread(run_official_script, bridge_script, 30)
                    report.append(f"• Bridge via `{bridge_script.name}`: código de saída={result.returncode}")
                except Exception as exc:
                    report.append(f"• Bridge via `{bridge_script.name}` falhou ao executar: {exc}")
            else:
                report.append("• Bridge: ❌ nenhum inicializador oficial encontrado em "
                               f"{AURA_ROOT / 'scripts' / 'bridge'}. Serviço não iniciado.")

            report.append("• Engine: ❌ nenhum inicializador oficial dedicado foi localizado no projeto "
                           "(sem script próprio conhecido). Serviço não iniciado; evitando comando inventado.")

        ollama_online_before = tcp_check(*SERVICES["ollama"][:2])
        if ollama_online_before:
            report.append("• Ollama: 🟢 já estava ONLINE. Nenhuma ação necessária.")
        else:
            report.append("• Ollama: 🔴 OFFLINE e nenhum inicializador oficial foi localizado no projeto para "
                           "automatizá-lo. Não foi iniciado automaticamente; inicie manualmente o serviço/app Ollama.")

        await asyncio.sleep(2)
        snapshot = await asyncio.to_thread(collect_snapshot)
        report.append("\n📊 Status final após a tentativa:")
        report.append(snapshot_summary(snapshot))

        audit(
            "start_all_executed",
            scripts_used={k: v for k, v in used_scripts.items() if v},
            services_status={name: item.get("online") for name, item in snapshot.get("services", {}).items()},
        )
        return "\n".join(report)

    async def execute(self, action: str):
        if action == "ativar segura":
            return await self.run_safe_activation()
        if action == "iniciar tudo":
            return await self.run_start_all()
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
                url = payload.get("url", "")
                branch = payload.get("branch")
                label = safe_name(payload.get("agent") or url.rsplit("/", 1)[-1] or f"{kind}-{plan_id}")
                try:
                    result = await asyncio.to_thread(download_repo_archive, url, label, kind, branch)
                except Exception as exc:
                    plan["status"] = "STAGING_FALHOU"
                    PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                    audit("external_source_download_failed", plan_id=plan_id, url=url, error=str(exc))
                    return (f"❌ Aprovação registrada, mas o download para staging falhou: {exc}\n"
                            "Nenhum arquivo foi executado. Verifique a URL/branch e tente novamente.")
                plan["status"] = "STAGING_BAIXADO"
                plan["staged_path"] = result["path"]
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("external_source_downloaded_staging", plan_id=plan_id, url=url, path=result["path"], sha256=result.get("sha256"))
                reused_note = " (reaproveitado; já estava em staging)" if result.get("reused_existing") else ""
                risks = await asyncio.to_thread(scan_staged_for_risks, Path(result["path"]))
                risk_note = ("\n⚠️ Varredura estática encontrou padrões suspeitos — revise antes de `promover`:\n" +
                             "\n".join(f"  • {r}" for r in risks)) if risks else "\nVarredura estática: nenhum padrão suspeito encontrado (não substitui revisão manual)."
                return (f"✅ Baixado para staging{reused_note} (arquivo estático, sem `git clone`, nada executado): {result['path']}\n"
                        f"sha256={result.get('sha256')}\n"
                        f"{risk_note}\n"
                        "Revise arquivos, licença e dependências manualmente. Para ativar de verdade: "
                        f"`promover {label}` (pede uma nova confirmação). Nenhum setup.py, Makefile ou instalador foi rodado.")
            if kind == "promote_staged":
                staged_dir = Path(payload["staged_dir"])
                if STAGING_ROOT.resolve() not in staged_dir.resolve().parents:
                    return "❌ Caminho de staging rejeitado pela política de área."
                try:
                    destination, backup = await asyncio.to_thread(promote_staged_item, staged_dir)
                except Exception as exc:
                    plan["status"] = "PROMOCAO_FALHOU"
                    PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                    audit("staged_promotion_failed", plan_id=plan_id, staged_dir=str(staged_dir), error=str(exc))
                    return f"❌ Promoção falhou: {exc}. Nada foi movido ou sobrescrito."
                plan["status"] = "PROMOVIDO"
                PLANS_FILE.write_text(json.dumps(plans[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
                audit("staged_item_promoted", plan_id=plan_id, staged_dir=str(staged_dir), destination=str(destination), backup=str(backup) if backup else None)
                return (f"✅ Promovido para área ativa: {destination}. Backup do destino anterior: {backup or 'não necessário'}.\n"
                        "Ainda nenhum instalador foi executado — se o pacote precisar de setup próprio, isso continua manual.")
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
                return await ask_ollama(f"PEDIDO DO USUÁRIO: {value}\nARQUIVO ENCONTRADO: {target}\nCONTEÚDO:\n{content}", snapshot)
        if kind == "full_spec":
            self.dialogue = None
            return await self.prepare_full_spec(value or "")
        if kind == "status":
            snapshot = await asyncio.to_thread(collect_snapshot)
            show_status(snapshot)
            return None
        if kind == "help":
            return self.help()
        if kind == "discover_skills":
            return await self.discover_skills()
        if kind == "list_staging":
            return await self.show_staging()
        if kind == "cancel":
            self.pending_action = None
            return "✅ Ação cancelada. Nada foi alterado."
        if kind in {"repair_plan", "create_agent", "edit_agent", "order_tasks", "install_skill", "install_repo", "train_agent", "promote_staged"}:
            return await self.administrative_plan(kind, value or "")
        if kind == "action":
            return self.ask_confirmation(value)
        if kind == "confirm":
            if self.pending_action and value == self.pending_action:
                action = self.pending_action
                self.pending_action = None
                return await self.execute(action)
            return "❌ Confirmação não corresponde a nenhuma ação pendente. Digite AJUDA."
        snapshot = await asyncio.to_thread(collect_snapshot)
        async with self.model_lock:
            result = await ask_ollama(raw, snapshot, self.history)
        self.history.append((raw, result))
        del self.history[:-self.max_history_turns]
        await asyncio.to_thread(save_chat_history, self.history)
        return result

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

    async def run(self):
        ensure_control_dirs()
        self.history = await asyncio.to_thread(load_chat_history)
        title(f"🤖 Harness Supervisor Pro\nModelo: {MODEL} · Retenção: {KEEP_ALIVE} · Contexto: {NUM_CTX}\n🛡️ Paper trade ativo · Execução real bloqueada · Reparo controlado")
        try:
            print_complete(await self.discover_skills())
        except Exception as exc:
            out(f"⚠️ Descoberta automática de skills falhou nesta sessão (seguindo normalmente): {exc}", "yellow")
        input_task = asyncio.create_task(self.input_loop())
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
        input_task.cancel()


def self_test() -> None:
    assert KEEP_ALIVE not in {"0", "0s", "0m"}
    assert os.environ.get("PAPER_TRADE") == "true"
    assert os.environ.get("EXECUTION_ALLOWED") == "false"
    assert repo_url("https://github.com/org/repo") == "https://github.com/org/repo"
    assert "PAPER_TRADE" not in _SAFE_ENV_OVERRIDABLE
    assert "EXECUTION_ALLOWED" not in _SAFE_ENV_OVERRIDABLE
    assert _archive_candidate_urls("https://github.com/org/repo")[0].startswith("https://codeload.github.com/org/repo/")

    # Garante que a extração segura recusa um membro que tenta escapar da pasta de staging.
    with tempfile.TemporaryDirectory() as tmp:
        evil_archive = Path(tmp) / "evil.tar.gz"
        with tarfile.open(evil_archive, "w:gz") as archive:
            info = tarfile.TarInfo(name="../escaped.txt")
            info.size = 0
            archive.addfile(info, io.BytesIO(b""))
        dest = Path(tmp) / "dest"
        dest.mkdir()
        try:
            _safe_extract_tar(evil_archive, dest)
            raise AssertionError("extração deveria ter recusado o path traversal")
        except ValueError:
            pass
    print("Harness self-test: OK; modo seguro ativo; nenhuma alteração executada.")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
        raise SystemExit(0)
    try:
        asyncio.run(Halem().run())
    except KeyboardInterrupt:
        print("\n[INFO] Supervisor encerrado.")
# ============================================================================
# AURA / HARNESS — BLOCO ÚNICO DE CORREÇÃO E MELHORIA
# ----------------------------------------------------------------------------
# Cole este bloco INTEIRO no FINAL do arquivo, imediatamente ANTES da linha
# `if __name__ == "__main__":` (ou antes do asyncio.run/main do final).
#
# Nada do arquivo original é apagado: as funções corrigidas abaixo usam os
# MESMOS nomes das originais e as sobrescrevem em tempo de execução (Python
# usa sempre a última definição carregada). Todo o restante é adição pura.
#
# Correções aplicadas (motivos pelos quais .bat/.exe não subiam):
#   1) .exe não era aceito em run_official_script()/localizadores;
#   2) subprocess.run(timeout=45, capture_output=True) esperava o serviço
#      TERMINAR (TimeoutExpired / pipes herdados travados / chat congelado);
#   3) find_in_dir_by_hint() devolvia None por empate falso com stop_*.bat;
#   4) busca restrita à raiz; engine não tinha resolvedor;
#   5) text=True sem errors="replace" podia derrubar com UnicodeDecodeError.
# ============================================================================

try:
    from rich.rule import Rule
    RICH_RULE = True
except Exception:
    RICH_RULE = False

# ---------------------------------------------------------------------------
# CORREÇÃO 1 — .exe passa a ser inicializador válido em todo o harness.
# ---------------------------------------------------------------------------
RUNNABLE_SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".py", ".sh", ".exe"}

# Logs dos inicializadores (área controlada; o modelo nunca escreve aqui).
STARTER_LOGS_ROOT = CONTROL_ROOT / "logs"

# Pistas NEGATIVAS: arquivos de parada/instalação/verificação não servem para
# INICIAR. Antes, "stop_bridge.bat" empatava com "start_bridge.bat" e o
# resolvedor devolvia None mesmo com o starter certo presente no disco.
STARTER_NEGATIVE_HINTS = (
    "stop", "parar", "kill", "deslig", "encerra", "finaliz",
    "instal", "recuper", "repar", "monitor", "verific", "diag",
    "test", "teste", "limpa", "clean", "reset", "backup",
)

# Pastas oficiais (dentro da raiz do projeto) onde cada serviço pode ter
# inicializador. Nenhuma pasta fora da raiz da AURA é consultada.
SERVICE_STARTER_DIRS = {
    "engine": [AURA_ROOT / "engine", AURA_ROOT / "scripts" / "engine", AURA_ROOT / "scripts", AURA_ROOT],
    "bridge": [AURA_ROOT / "scripts" / "bridge", AURA_ROOT / "bridge", AURA_ROOT / "scripts", AURA_ROOT],
    "voice": [AURA_ROOT / "voice", AURA_ROOT / "scripts" / "voice", AURA_ROOT / "scripts", AURA_ROOT],
    "ollama": [AURA_ROOT / "scripts", AURA_ROOT],
}

SERVICE_STARTER_HINTS = {
    "engine": ("engine", "start", "iniciar", "run", "up", "servidor", "server"),
    "bridge": ("bridge", "start", "iniciar", "run", "up"),
    "voice": ("voice", "voz", "start", "iniciar", "run", "up"),
    "ollama": ("ollama", "start", "iniciar", "run", "up"),
}


# ---------------------------------------------------------------------------
# CORREÇÃO 2 — find_in_dir_by_hint robusto (mesma assinatura, mesma política).
# ---------------------------------------------------------------------------
def find_in_dir_by_hint(directory: Path, hints: tuple[str, ...]) -> Path | None:
    """CORRIGIDO: procura um inicializador oficial dentro de um diretório oficial.
    Aceita .exe agora; ignora pistas negativas (stop/parar/instalar/verificar...);
    escolhe o candidato com mais pistas casadas (desempate: nome mais curto).
    Só devolve None quando não há candidato ou quando os dois melhores empatam
    de verdade — aí a ambiguidade é real e não arriscamos o script errado."""
    try:
        if not directory.is_dir():
            return None
    except OSError:
        return None
    scored: list[tuple[int, int, Path]] = []
    for entry in directory.iterdir():
        try:
            if not entry.is_file() or entry.suffix.lower() not in RUNNABLE_SCRIPT_SUFFIXES:
                continue
        except OSError:
            continue
        name = _normalized_filename(entry.name)
        if any(negative in name for negative in STARTER_NEGATIVE_HINTS):
            continue
        score = sum(1 for hint in hints if hint in name)
        if score:
            scored.append((score, len(entry.name), entry))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][1] == scored[1][1]:
        return None
    return scored[0][2]


# ---------------------------------------------------------------------------
# CORREÇÃO 3 — run_official_script aceita .exe e não derruba com encoding.
# ---------------------------------------------------------------------------
def run_official_script(path: Path, timeout: int = 45) -> subprocess.CompletedProcess:
    """CORRIGIDO: executa apenas scripts oficiais já existentes (nunca linha de
    comando construída na hora). Correções: aceita .exe (executa o binário
    diretamente) e usa errors="replace" (saída de .bat em cp850 não derruba mais
    com UnicodeDecodeError). Assinatura e timeout mantidos.
    ATENÇÃO: use apenas para scripts que TERMINAM (instalador, verificador).
    Inicializador de serviço (engine/bridge/voice) fica RODANDO — para esses use
    run_official_starter_detached(), senão volta o problema do timeout/pipe."""
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    elif suffix in {".bat", ".cmd"}:
        command = ["cmd", "/c", str(path)]
    elif suffix == ".py":
        command = [sys.executable, str(path)]
    elif suffix == ".sh":
        command = ["bash", str(path)]
    elif suffix == ".exe":
        command = [str(path)]
    else:
        raise ValueError(f"extensão de script não suportada para execução: {suffix}")
    return subprocess.run(
        command,
        cwd=str(path.parent),
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


async def run_official_script_async(path: Path, timeout: int = 45) -> subprocess.CompletedProcess:
    """NOVO: run_official_script sem congelar o event loop do chat (roda em
    thread separada via asyncio.to_thread). Use em funções async."""
    return await asyncio.to_thread(run_official_script, path, timeout)


# ---------------------------------------------------------------------------
# ADIÇÃO 1 — inicializador desanexado (é isto que faltava para subir tudo).
# ---------------------------------------------------------------------------
def run_official_starter_detached(path: Path, visible_console: bool = True) -> dict:
    """NOVO: inicia um inicializador oficial (.bat/.cmd/.ps1/.py/.sh/.exe) como
    processo SEPARADO do harness, sem capturar pipes e sem esperar terminar.
    Resolve exatamente o que travava antes:
      • subprocess.run(timeout=45) esperava o serviço terminar (ele nunca
        termina) → TimeoutExpired → ação registrada como falha;
      • capture_output=True mantinha pipes herdados pelo servidor → deadlock
        até o timeout (harness 'congelado');
      • .exe nem era aceito.
    Comportamento novo: por padrão abre janela própria (igual a dar dois cliques
    no .bat). Com visible_console=False, roda oculto e a saída vai para log em
    halem_control/logs/ (stdin=DEVNULL: pause/choice em .bat não travam).
    Nunca executa nada além do arquivo oficial recebido; tudo é auditado."""
    suffix = path.suffix.lower()
    if suffix == ".ps1":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    elif suffix in {".bat", ".cmd"}:
        command = ["cmd", "/c", str(path)]
    elif suffix == ".py":
        command = [sys.executable, str(path)]
    elif suffix == ".sh":
        command = ["bash", str(path)]
    elif suffix == ".exe":
        command = [str(path)]
    else:
        raise ValueError(f"extensão de inicializador não suportada: {suffix}")
    STARTER_LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    label = re.sub(r"[^a-z0-9_-]+", "-", normalize(path.stem)).strip("-")[:48] or "starter"
    log_path = STARTER_LOGS_ROOT / f"{label}-{int(time.time())}.log"
    stdout_arg = None
    stderr_arg = None
    stdin_arg = None
    creationflags = 0
    start_new_session = False
    log_handle = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE if visible_console else subprocess.CREATE_NO_WINDOW
    else:
        start_new_session = True
    if not visible_console or os.name != "nt":
        log_handle = log_path.open("ab")
        stdout_arg = log_handle
        stderr_arg = subprocess.STDOUT
        stdin_arg = subprocess.DEVNULL
    try:
        process = subprocess.Popen(
            command,
            cwd=str(path.parent),
            stdin=stdin_arg,
            stdout=stdout_arg,
            stderr=stderr_arg,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
    finally:
        if log_handle is not None:
            log_handle.close()  # o processo filho mantém a própria cópia herdada
    record = {
        "starter": str(path),
        "command": command,
        "pid": process.pid,
        "log": str(log_path) if log_handle is not None else None,
        "visible_console": visible_console,
        "started_at": utc_now(),
    }
    audit("starter_launched", **record)
    return record


def read_starter_log_tail(log_path: str | Path, max_chars: int = 1200) -> str:
    """NOVO: lê o fim do log de um inicializador (somente leitura) para explicar
    no chat por que o serviço não subiu. Tolerante a ausência/encoding."""
    try:
        path = Path(log_path)
        if not path.is_file():
            return ""
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_chars * 4))
            data = handle.read()
        return data.decode("utf-8", errors="replace")[-max_chars:]
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# ADIÇÃO 2 — localizadores de inicializador por serviço (engine incluído).
# ---------------------------------------------------------------------------
def find_service_starter(service_key: str) -> Path | None:
    """NOVO: procura o inicializador de um serviço em pastas oficiais.
      • só olha pastas oficiais do projeto (SERVICE_STARTER_DIRS);
      • ignora pistas negativas (stop/parar/instalar/verificar/...);
      • em pastas genéricas (raiz, scripts) exige o nome do serviço no arquivo
        (evita pegar 'iniciar_voz.bat' para subir o engine);
      • em pasta própria do serviço (engine/, scripts/bridge, voice/) aceita
        também nomes genéricos como start.bat / run.py / servidor.exe;
      • escolhe deterministicamente quem tem mais pistas de início
        (desempate: nome mais curto, depois ordem alfabética)."""
    if service_key not in SERVICE_STARTER_HINTS:
        return None
    required = {"engine": ("engine",), "bridge": ("bridge",), "voice": ("voice", "voz"), "ollama": ("ollama",)}[service_key]
    hints = SERVICE_STARTER_HINTS[service_key]
    best: tuple[int, int, Path] | None = None
    for directory in SERVICE_STARTER_DIRS[service_key]:
        try:
            if not directory.is_dir():
                continue
            dir_token_ok = any(token in _normalized_filename(str(directory)) for token in required)
            for entry in sorted(directory.iterdir()):
                try:
                    if not entry.is_file() or entry.suffix.lower() not in RUNNABLE_SCRIPT_SUFFIXES:
                        continue
                except OSError:
                    continue
                name = _normalized_filename(entry.name)
                if any(negative in name for negative in STARTER_NEGATIVE_HINTS):
                    continue
                if not dir_token_ok and not any(token in name for token in required):
                    continue
                score = sum(1 for hint in hints if hint in name)
                candidate = (score, -len(entry.name))
                if best is None or candidate > (best[0], best[1]):
                    best = (score, -len(entry.name), entry)
        except OSError:
            continue
    return best[2] if best is not None else None


def resolve_engine_starter() -> Path | None:
    """NOVO: resolvedor do Engine (não existia). Nomes conhecidos primeiro;
    depois busca com pista obrigatória em pastas oficiais."""
    exact = find_existing([
        AURA_ROOT / "iniciar_engine.bat",
        AURA_ROOT / "iniciar_engine.exe",
        AURA_ROOT / "start_engine.bat",
        AURA_ROOT / "start_engine.exe",
    ])
    if exact:
        return exact
    return find_service_starter("engine")


def resolve_bridge_starter() -> Path | None:
    """CORRIGIDO: mantém a busca original em scripts/bridge e adiciona fallback
    (pasta própria + scripts + raiz), sem inventar nomes; aceita .exe agora."""
    original = find_in_dir_by_hint(AURA_ROOT / "scripts" / "bridge", ("bridge", "start", "iniciar", "run", "up"))
    if original:
        return original
    return find_service_starter("bridge")


def resolve_voice_starter() -> Path | None:
    """CORRIGIDO: mantém os nomes oficiais conhecidos (iniciar_voz.bat/.sh) e
    adiciona .exe e busca por pista em pastas oficiais como fallback."""
    exact = find_existing([
        AURA_ROOT / "iniciar_voz.bat",
        AURA_ROOT / "iniciar_voz.exe",
        AURA_ROOT / "iniciar_voz.sh",
    ])
    if exact:
        return exact
    return find_service_starter("voice")


def resolve_ollama_starter() -> Path | None:
    """NOVO: o Ollama é serviço externo; só usamos um inicializador se o projeto
    já tiver um — nunca executamos 'ollama serve' inventado na hora."""
    exact = find_existing([
        AURA_ROOT / "iniciar_ollama.bat",
        AURA_ROOT / "iniciar_ollama.exe",
        AURA_ROOT / "start_ollama.bat",
    ])
    if exact:
        return exact
    return find_service_starter("ollama")


def resolve_master_starter() -> Path | None:
    """CORRIGIDO: mantém os nomes oficiais originais e adiciona a variante .exe
    do inicializador 'sobe tudo'."""
    return find_existing([
        AURA_ROOT / "INSTALAR_E_INICIAR_TUDO.bat",
        AURA_ROOT / "INSTALAR_E_INICIAR_TUDO.exe",
        AURA_ROOT / "RECUPERAR_AURA_SERVICOS.ps1",
        AURA_ROOT / "RECUPERAR_AURA_SERVICOS.bat",
    ])


def find_official_stop_script(service_key: str) -> Path | None:
    """NOVO: procura script oficial de PARADA (stop/parar + nome do serviço).
    Se não existir, devolve None — nunca inventamos comando de parada nem
    matamos processo por fora."""
    if service_key not in SERVICES:
        return None
    tokens = ("voice", "voz") if service_key == "voice" else (service_key,)
    for directory in SERVICE_STARTER_DIRS.get(service_key, []):
        try:
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                try:
                    if not entry.is_file() or entry.suffix.lower() not in RUNNABLE_SCRIPT_SUFFIXES:
                        continue
                except OSError:
                    continue
                name = _normalized_filename(entry.name)
                if ("stop" in name or "parar" in name) and any(token in name for token in tokens):
                    return entry
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
# ADIÇÃO 3 — espera real (porta + health) e orquestrador por serviço.
# ---------------------------------------------------------------------------
def wait_service_online(service_name: str, timeout: float = 40.0) -> dict:
    """NOVO: espera o serviço responder DE VERDADE (porta + health), em vez de
    assumir sucesso só porque o .bat foi executado. Retorna dicionário, sem
    lançar exceção."""
    if service_name not in SERVICES:
        raise ValueError(f"serviço desconhecido: {service_name}")
    host, port, health_path = SERVICES[service_name]
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if tcp_check(host, port):
            health = http_json(f"http://{host}:{port}{health_path}")
            return {
                "service": service_name,
                "online": True,
                "waited_s": round(time.monotonic() - started, 1),
                "health_online": health.get("online"),
                "latency_ms": health.get("latency_ms"),
            }
        time.sleep(0.5)
    return {"service": service_name, "online": False, "waited_s": round(time.monotonic() - started, 1)}


SERVICE_START_RESOLVERS = {
    "engine": resolve_engine_starter,
    "bridge": resolve_bridge_starter,
    "voice": resolve_voice_starter,
    "ollama": resolve_ollama_starter,
}


def start_aura_service(service_key: str, visible_console: bool = True, wait_timeout: float = 40.0) -> dict:
    """NOVO: sobe UM serviço da AURA usando somente inicializadores oficiais já
    existentes em disco, sem travar o harness:
      1) se a porta já responde, não faz nada (idempotente);
      2) resolve o inicializador (nomes conhecidos + pistas em pastas oficiais;
         .bat/.cmd/.ps1/.py/.sh/.exe);
      3) lança desanexado (run_official_starter_detached);
      4) espera porta/health responder (wait_service_online);
      5) audita tudo e devolve relatório.
    Política inalterada: paper trade e execução real seguem bloqueados — aqui
    apenas se executa arquivo que JÁ existe no projeto, como se alguém desse
    dois cliques nele."""
    if service_key not in SERVICES:
        raise ValueError(f"serviço desconhecido: {service_key}")
    host, port, _health_path = SERVICES[service_key]
    result = {"service": service_key, "already_online": False, "starter": None, "launch": None, "wait": None, "error": None}
    if tcp_check(host, port):
        result["already_online"] = True
        result["wait"] = {"online": True, "waited_s": 0.0}
        audit("service_start_skipped", service=service_key, reason="already_online", port=port)
        return result
    starter = SERVICE_START_RESOLVERS[service_key]()
    if starter is None:
        result["error"] = (
            "nenhum inicializador oficial encontrado para '" + service_key + "' "
            "(procurado em: " + ", ".join(str(directory) for directory in SERVICE_STARTER_DIRS[service_key]) + ")"
        )
        if service_key == "ollama":
            result["error"] += " — para o Ollama, inicie pelo próprio programa/app dele; o harness não inventa comando externo."
        audit("service_start_failed", service=service_key, reason="starter_not_found")
        return result
    result["starter"] = str(starter)
    try:
        result["launch"] = run_official_starter_detached(starter, visible_console=visible_console)
    except Exception as exc:
        result["error"] = f"falha ao lançar {starter}: {exc}"
        audit("service_start_failed", service=service_key, starter=str(starter), error=str(exc))
        return result
    result["wait"] = wait_service_online(service_key, timeout=wait_timeout)
    audit("service_start_result", service=service_key, starter=str(starter), online=result["wait"].get("online"))
    return result


def format_service_start_report(result: dict) -> str:
    """NOVO: transforma o resultado de start_aura_service em linha curta de chat."""
    name = str(result.get("service", "?")).upper()
    if result.get("error"):
        return f"🔴 {name}: {result['error']}"
    if result.get("already_online"):
        port = SERVICES.get(result.get("service", ""), ("", 0, ""))[1]
        return f"🟢 {name}: já estava online (porta {port}); nada a fazer."
    wait = result.get("wait") or {}
    starter_name = Path(result.get("starter") or "?").name
    launch = result.get("launch") or {}
    if wait.get("online"):
        return f"🟢 {name}: online em {wait.get('waited_s')}s via {starter_name}."
    tail = read_starter_log_tail(launch.get("log")) if launch.get("log") else ""
    message = (f"🟡 {name}: {starter_name} foi lançado (PID {launch.get('pid')}), "
               f"mas a porta não respondeu em {wait.get('waited_s')}s.")
    if tail:
        message += f" Últimas linhas do log:\n{tail}"
    elif launch.get("visible_console"):
        message += " Veja a janela aberta do serviço para diagnosticar."
    return message


def report_found_starters() -> str:
    """NOVO (somente leitura): mostra qual inicializador oficial seria usado
    para cada serviço — para conferir a resolução sem iniciar nada."""
    lines = []
    master = resolve_master_starter()
    lines.append(f"mestre  : {master if master is not None else 'não encontrado'}")
    for key in ("engine", "bridge", "voice", "ollama"):
        starter = SERVICE_START_RESOLVERS[key]()
        lines.append(f"{key:7s}: {starter if starter is not None else 'não encontrado'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ADIÇÃO 4 — executor das ações 'iniciar/reiniciar ...' (fluxo CONFIRMAR igual).
# ---------------------------------------------------------------------------
async def execute_start_action(action: str, visible_console: bool = True) -> str:
    """NOVO executor para as ações JÁ declaradas em MUTATING_ACTIONS
    ('iniciar tudo', 'iniciar engine', 'iniciar bridge', 'iniciar voice',
    'reiniciar engine/bridge/voice'). Chame no ponto onde essas ações eram
    executadas, DEPOIS do plano + CONFIRMAR (fluxo inalterado). Todas as
    esperas rodam em asyncio.to_thread: o chat continua vivo enquanto os
    serviços sobem."""
    text = normalize(action)
    lines: list[str] = []

    if "tudo" in text:
        master = resolve_master_starter()
        if master is not None:
            launch = run_official_starter_detached(master, visible_console=visible_console)
            lines.append(f"🚀 Inicializador mestre oficial executado: {master.name} (PID {launch['pid']}).")
            keys = ("ollama", "engine", "bridge", "voice")
            waits = await asyncio.gather(*(asyncio.to_thread(wait_service_online, key, 30.0) for key in keys))
            for key, wait in zip(keys, waits):
                if wait.get("online"):
                    lines.append(f"🟢 {key.upper()}: online em {wait.get('waited_s')}s.")
                else:
                    lines.append(f"🟡 {key.upper()}: não respondeu após o inicializador mestre.")
        else:
            lines.append("ℹ️ Inicializador mestre não encontrado na raiz do projeto; subindo serviço por serviço.")
        for key in ("ollama", "engine", "bridge", "voice"):
            host, port, _health = SERVICES[key]
            if tcp_check(host, port):
                continue
            result = await asyncio.to_thread(start_aura_service, key, visible_console, 40.0)
            lines.append(format_service_start_report(result))
        return "\n".join(lines)

    key = None
    if "engine" in text:
        key = "engine"
    elif "bridge" in text:
        key = "bridge"
    elif "voice" in text or "voz" in text:
        key = "voice"
    elif "ollama" in text:
        key = "ollama"
    if key is None:
        return "Não reconheci o serviço. Use: iniciar engine | iniciar bridge | iniciar voice | iniciar tudo."

    host, port, _health = SERVICES[key]
    if text.startswith("reiniciar") and tcp_check(host, port):
        stopper = find_official_stop_script(key)
        if stopper is not None:
            lines.append(f"⏹ Parando {key.upper()} pelo script oficial {stopper.name}…")
            try:
                done = await run_official_script_async(stopper, 30)
                lines.append(f"⏹ Script de parada encerrou (código {done.returncode}).")
            except Exception as exc:
                lines.append(f"⚠️ Script de parada falhou: {exc}")
            for _ in range(20):
                if not tcp_check(host, port):
                    break
                await asyncio.sleep(0.5)
        else:
            lines.append(f"ℹ️ {key.upper()} já está online e não achei script oficial de parada; tentando subir de novo mesmo assim.")

    result = await asyncio.to_thread(start_aura_service, key, visible_console, 40.0)
    lines.append(format_service_start_report(result))
    return "\n".join(lines)


def execute_start_action_sync(action: str, visible_console: bool = True) -> str:
    """NOVO: variante síncrona para trechos que ainda não são async.
    Não use dentro de um event loop ativo (nesse caso, await execute_start_action)."""
    return asyncio.run(execute_start_action(action, visible_console))


# ============================================================================
# MELHORIA — LAYOUT DO CHAT (diferencia VOCÊ do AGENTE)
# ----------------------------------------------------------------------------
# Como ligar no seu laço de chat (nada é removido):
#   1) logo DEPOIS de ler a linha do usuário, chame:  print_chat_turn("user", raw)
#   2) onde a resposta é exibida hoje, chame:          print_chat_turn("agent", resposta)
#   3) opcional, ao entrar no chat:                    print_chat_layout_banner()
# ============================================================================
def _chat_role_label(role: str) -> str:
    if role == "user":
        return ("🧑 " if EMOJI else "") + "HALem (você)"
    return ("🤖 " if EMOJI else "") + "AURA / Harness"


def print_chat_layout_banner() -> None:
    """NOVO: legenda do layout, para ficar claro quem escreveu o quê."""
    if RICH:
        if RICH_RULE:
            console.print(Rule("Layout do chat", style="cyan"))
        else:
            console.print("[bold cyan]Layout do chat[/bold cyan]")
        console.print("[magenta]»  o que VOCÊ (HALem) escreve[/magenta]")
        console.print("[cyan]«  o que o AGENTE (AURA/Harness) responde[/cyan]")
    else:
        print("»  o que VOCÊ (HALem) escreve")
        print("«  o que o AGENTE (AURA/Harness) responde")


def print_chat_turn(role: str, text: str) -> None:
    """NOVO: imprime um turno do chat com layout visual distinto:
      • usuário → cabeçalho magenta com '»' + corpo magenta;
      • agente  → cabeçalho ciano com '«' + corpo impresso integral
                  (reaproveita print_complete, sem cortar nada).
    O carimbo de hora em cada turno deixa a ordem da conversa óbvia."""
    if role not in ("user", "agent"):
        role = "agent"
    body = (text or "").strip()
    if not body:
        return
    label = _chat_role_label(role)
    arrow = "»" if role == "user" else "«"
    stamp = time.strftime("%H:%M:%S")
    if RICH:
        style = "magenta" if role == "user" else "cyan"
        header = f"{arrow} {label} · {stamp}"
        if RICH_RULE:
            console.print(Rule(header, style=style))
        else:
            console.print(f"[bold {style}]{header}[/bold {style}]")
        if role == "user":
            console.print(body, style="magenta", markup=False, soft_wrap=True)
        else:
            print_complete(body)
        if RICH_RULE:
            console.print(Rule(style=style))
        else:
            console.print("─" * 60, style=style)
    else:
        print(f"{arrow} {label} · {stamp}")
        print("-" * 60)
        print(body)
        print("-" * 60)
        {
  "name": "agente-especificacao-1788586096",
  "purpose": "Especificação de novo agente",
  "enabled": false,
  "approval_required": true,
  "instructions": "Gostaria de um diagnóstico consolidado do sistema AURA. Considere que o harness acabou de subir, que o Ollama roda localmente em 127.0.0.1:11434 com o modelo qwen3:8b residente com keep_alive de 24h, que os serviços oficiais são Engine na porta 8765 com health em /api/health, Bridge na 8080 em /health e Voice na 8099 em /api/health, e que os inicializadores oficiais são arquivos .bat e .exe já existentes no projeto sob C:\\aura. A política de segurança é paper trade ativo, execução real bloqueada, reparo desativado, e toda ação com efeito exige plano e confirmação textual exata CONFIRMAR. Quero que você verifique o estado atual dos quatro serviços, aponte quais estão offline, proponha qual ação única devo aprovar para normalizar tudo, e me lembre em uma linha o que a auditoria registraria se eu aprovar. Não me faça perguntas, não liste comandos genéricos, não repita o diagnóstico completo do status: só o resumo, a ação recomendada e a nota de auditoria.",
  "capabilities": [
    "diagnostico_servicos",
    "resumo_executivo",
    "proposta_acao_unica"
  ],
  "tasks": [
    "Verificar conectividade das portas 11434 (Ollama), 8765 (Engine), 8080 (Bridge) e 8099 (Voice), coletando health de cada uma.",
    "Listar somente os serviços offline e o impacto imediato de cada um.",
    "Propor uma única ação normalizadora (por exemplo: iniciar tudo) para aprovação via CONFIRMAR.",
    "Entregar o resultado em até 4 linhas: resumo, ação recomendada e a nota de auditoria correspondente."
  ],
  "created_at": "2026-09-05T05:28:16.762300+00:00"
} # ============================================================================
# AURA / HARNESS — BLOCO ÚNICO v2
# Cole no FINAL do arquivo, imediatamente ANTES de `if __name__ == "__main__":`.
# Nada é removido: as funções abaixo usam os MESMOS nomes das originais e as
# sobrescrevem; todo o restante é adição.
#
#   1) DESCoberta de skills: 1 opção por vez, sempre uma pesquisa NOVA
#      (memória persistente do que já foi mostrado + rotação de consulta).
#   2) CTRL+X encerra o supervisor no Windows (Ctrl+C continua valendo).
#   3) CHAT endurecido: o modelo não responde mais como "instalador"
#      (aqueles JSON falsos do log); pedidos de skill/repositório recebem
#      resposta determinística com o comando correto.
# ============================================================================

import builtins
from datetime import timedelta

try:
    import msvcrt  # Windows: captura tecla-a-tecla para o Ctrl+X
    MSVCRT_OK = True
except ImportError:
    MSVCRT_OK = False

# ---------------------------------------------------------------------------
# 1) MEMÓRIA DA DESCOBERTA — o que já foi mostrado, para nunca repetir
# ---------------------------------------------------------------------------
SKILL_DISCOVERY_MEMORY_FILE = CONTROL_ROOT / "skill_discovery_memory.json"
AURA_DISCOVERY_MAX_NEW = int(os.environ.get("AURA_DISCOVERY_MAX_NEW", "1"))

_VARIETY_KEYWORDS = (
    "mcp", "rag", "agent framework", "automation", "voice assistant", "tts",
    "speech recognition", "cli tool", "local llm", "ollama", "agent memory",
    "scheduler", "monitoring", "websocket", "trading bot", "quant",
    "data pipeline", "vector database", "prompt tools", "workflow",
    "observability", "toolkit", "llm gateway", "function calling",
)
_VARIETY_SORTS = ("updated", "stars")
_DISCOVERY_BASE_QUERIES = (
    "mcp server", "ai agent", "local llm tools", "automation cli",
    "voice assistant", "rag pipeline", "agent memory", "observability",
    "workflow automation", "vector database", "llm gateway", "tool calling",
)


def _load_discovery_memory() -> dict:
    data = read_json(SKILL_DISCOVERY_MEMORY_FILE)
    memory = data if isinstance(data, dict) else {}
    if not isinstance(memory.get("shown"), list):
        memory["shown"] = []
    if not isinstance(memory.get("calls"), int):
        memory["calls"] = 0
    return memory


def _save_discovery_memory(memory: dict) -> None:
    try:
        ensure_control_dirs()
        memory["shown"] = [str(name) for name in memory.get("shown", [])][-200:]
        SKILL_DISCOVERY_MEMORY_FILE.write_text(
            json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # persistência é best-effort; nunca deve travar a descoberta.


def _fresh_date_qualifier(days: int = 120) -> str:
    """Qualificador GitHub 'pushed:>data' — prioriza repositórios com atividade
    recente, em vez do topo de estrelas que nunca muda."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    return f"pushed:>{cutoff}"


def search_github_repos(query: str, max_results: int = 4) -> list[dict]:
    """SOBRESCRITO: sempre uma pesquisa NOVA. Cada chamada rotaciona
    palavra-chave, ordem (updated/stars) e filtro de data, e devolve no máximo
    AURA_DISCOVERY_MAX_NEW repositório(s) que AINDA NÃO foram mostrados antes
    (memória persistente). Por isso cada inicialização traz novidade, em vez
    das mesmas 9 de sempre. Mesma política da original: somente leitura, sem
    token, falha silenciosa, cache em memória."""
    if not GITHUB_DISCOVERY:
        return []
    memory = _load_discovery_memory()
    memory["calls"] = int(memory.get("calls", 0)) + 1
    shown = {str(name) for name in memory.get("shown", [])}
    keyword = _VARIETY_KEYWORDS[memory["calls"] % len(_VARIETY_KEYWORDS)]
    sort_field = _VARIETY_SORTS[memory["calls"] % len(_VARIETY_SORTS)]
    attempts = (
        f"{query} {keyword} {_fresh_date_qualifier(120)}",
        f"{query} {keyword}",
        f"{query} {_fresh_date_qualifier(120)}",
        query,
    )
    fetched: list[dict] = []
    for attempt in attempts:
        cache_key = f"{attempt}|{sort_field}|{max_results}"
        cached = _GITHUB_SEARCH_CACHE.get(cache_key)
        if cached and (time.time() - cached[0]) < GITHUB_CACHE_TTL_SECONDS:
            fetched = cached[1]
        else:
            try:
                params = urllib.parse.urlencode(
                    {"q": attempt, "sort": sort_field, "order": "desc", "per_page": 12}
                )
                request = urllib.request.Request(
                    f"https://api.github.com/search/repositories?{params}",
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "AURA-Harness/1.0"},
                    method="GET",
                )
                with urllib.request.urlopen(request, timeout=4.0) as response:
                    data = json.loads(response.read().decode("utf-8", errors="replace"))
                fetched = []
                for item in data.get("items", [])[:12]:
                    fetched.append({
                        "name": item.get("full_name"),
                        "url": item.get("html_url"),
                        "stars": item.get("stargazers_count"),
                        "description": (item.get("description") or "")[:200],
                        "updated_at": item.get("updated_at"),
                    })
                _GITHUB_SEARCH_CACHE[cache_key] = (time.time(), fetched)
            except Exception:
                fetched = []
        fresh = [item for item in fetched if item.get("name") and item.get("name") not in shown]
        if fresh:
            chosen = fresh[:max(1, AURA_DISCOVERY_MAX_NEW)]
            for item in chosen:
                shown.add(str(item.get("name")))
            memory["shown"] = sorted(shown)
            _save_discovery_memory(memory)
            return chosen
    _save_discovery_memory(memory)
    return fetched[:max(1, AURA_DISCOVERY_MAX_NEW)] if fetched else []


async def ask_ollama_skill_suggestions(snapshot: dict, local_skills: list[dict], real_candidates: list[dict] | None = None) -> str:
    """SOBRESCRITO: recomenda EXATAMENTE UMA skill (nunca lista/top-5), nunca
    repete o que já foi apresentado, responde em texto (nunca JSON) e mantém
    fallback determinístico se o modelo estiver offline. Instalação real
    continua exigindo 'instalar skill <url>' + CONFIRMAR."""
    memory = _load_discovery_memory()
    ja_apresentadas = [str(name) for name in memory.get("shown", [])][-40:]
    system = (
        "Você é o consultor de capacidades do Harness AURA. Sua tarefa é recomendar EXATAMENTE UMA (1) skill — "
        "nunca uma lista, nunca top-5. Se houver candidato real no contexto, comente apenas ele (nome, URL, uma "
        "frase de por que ajudaria a AURA, confiança 0–100%). Se não houver candidato real, diga somente que não "
        "há candidatos reais agora — não invente nomes, URLs ou estrelas. Não repita nada da lista "
        "'ja_apresentadas_antes'. Responda em português, texto corrido (nunca JSON), no máximo 6 linhas. Nunca "
        "afirme ter instalado, baixado, testado ou acessado algo. Termine lembrando que a instalação real exige o "
        "comando 'instalar skill <url>' seguido de confirmação explícita (CONFIRMAR); nada é instalado automaticamente."
    )
    context = {
        "servicos": snapshot.get("services", {}),
        "policy": snapshot.get("policy", {}),
        "skills_existentes": local_skills,
        "candidato_real": (real_candidates or [None])[0],
        "ja_apresentadas_antes": ja_apresentadas,
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"CONTEXTO:\n{json.dumps(context, ensure_ascii=False)[:6000]}\n\nRecomende UMA skill."},
        ],
        "stream": True,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_gpu": 99, "num_ctx": NUM_CTX, "num_predict": 384, "temperature": 0.4},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks: list[str] = []
    try:
        response = await asyncio.to_thread(urllib.request.urlopen, request, timeout=60)
        try:
            while True:
                line = await asyncio.to_thread(response.readline)
                if not line:
                    break
                part = json.loads(line.decode("utf-8", errors="replace"))
                text = part.get("message", {}).get("content", "")
                if text:
                    chunks.append(text)
                if part.get("done"):
                    break
        finally:
            response.close()
    except Exception:
        # Fallback determinístico: mantém "1 opção" mesmo com o modelo offline.
        if real_candidates:
            item = real_candidates[0]
            return (
                f"💡 {item.get('name')} ({item.get('stars')}★) — {item.get('url')}\n"
                f"{item.get('description') or ''}\n"
                "Sugestão determinística (modelo indisponível agora)."
            )
        return "⚠️ Sem candidatos reais e sem modelo disponível agora; nada a sugerir."
    return "".join(chunks).strip() or "Nenhuma sugestão retornada pelo modelo."


async def _single_skill_discovery_once() -> None:
    """NOVO: descoberta compacta — UMA skill nova por inicialização."""
    memory = _load_discovery_memory()
    base = _DISCOVERY_BASE_QUERIES[int(memory.get("calls", 0)) % len(_DISCOVERY_BASE_QUERIES)]
    candidates = search_github_repos(base, 4)  # já devolve no máximo 1 NOVA
    snapshot = collect_snapshot()
    local = list_local_skills()
    if RICH:
        console.print(Panel.fit("🎁 Skill sugerida agora — uma nova a cada inicialização", border_style="cyan"))
    else:
        print("=" * 60)
        print("Skill sugerida agora — uma nova a cada inicialização")
    if local:
        out(f"📦 Skills locais ({len(local)}): " + ", ".join(str(s.get("name")) for s in local[:8]))
    if not candidates:
        out("🔎 Nenhum candidato novo agora (sem rede, rate limit ou tudo já foi mostrado).")
        out("Para instalar: instalar skill <url> e depois CONFIRMAR (staging, sem executar nada).")
        return
    item = candidates[0]
    out(f"• {item.get('name')} ({item.get('stars')}★) — {item.get('url')}")
    if item.get("description"):
        out(f"  {item['description']}")
    text = await ask_ollama_skill_suggestions(snapshot, local, candidates)
    print_complete(text)
    out("Para instalar de verdade: instalar skill <url> e depois CONFIRMAR (baixa em staging, sem executar nada).")


def run_single_skill_discovery() -> None:
    """NOVO: use no boot (código síncrono, fora de funções async)."""
    try:
        asyncio.run(_single_skill_discovery_once())
    except RuntimeError as exc:
        out(f"⚠️ Descoberta não rodou aqui ({exc}). Dentro de código async, use: await run_single_skill_discovery_async()")


async def run_single_skill_discovery_async() -> None:
    """NOVO: variante para chamar com await dentro de funções async."""
    await _single_skill_discovery_once()


# ---------------------------------------------------------------------------
# 2) CHAT ENDURECIDO — mata o "instalador falso" (JSON de status) do log
# ---------------------------------------------------------------------------
_REPO_TOKEN_RE = re.compile(
    r"\b(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9_.-]{0,38}/[A-Za-z0-9_.-]{1,60}\b"
)
_INSTALL_VERBS = (
    "instal", "baix", "carreg", "verific", "instalad", "ativar", "ativ",
    "rodar", "execut", "adicion", "integr",
)


def _extract_repo_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _REPO_TOKEN_RE.finditer(text):
        token = match.group(0).rstrip(".,;:!?\"')")
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _redirect_repo_request(user_text: str) -> str | None:
    """NOVO: se a mensagem parece um pedido de skill/repositório (token
    dono/repo ou URL do GitHub/GitLab/Codeberg, com verbo de instalação ou
    mensagem curta), devolve resposta determinística SEM chamar o modelo.
    Foi exatamente o caso do log: 'zylon-ai/private-gpt headroom ...' virou
    JSON falso de instalação. Agora vira orientação correta, sem alucinação."""
    low = normalize(user_text)
    if not low:
        return None
    urls = re.findall(r"https?://(?:github|gitlab|codeberg)\S+", user_text, re.IGNORECASE)
    tokens = _extract_repo_tokens(user_text)
    if not urls and not tokens:
        return None
    wants_install = any(verb in low for verb in _INSTALL_VERBS)
    short_message = len(low) <= 80
    if not (wants_install or short_message):
        return None
    lines = [
        "🛑 Nada foi instalado nem verificado — o chat não tem poder de instalar nada.",
        "(Respostas anteriores em JSON vinham do modelo imitando um instalador; eram texto, não ações reais.)",
    ]
    if urls:
        lines.append(f"Para instalar de verdade: instalar skill {urls[0]} e depois CONFIRMAR.")
    elif tokens:
        suggested = f"https://github.com/{tokens[0]}"
        lines.append("Esses nomes parecem repositórios: " + ", ".join(tokens[:5]))
        lines.append(f"Comando correto (um por vez): instalar skill {suggested} e depois CONFIRMAR.")
    lines.append("Skills são repositórios por URL; modelos Ollama são gerenciados fora daqui (ex.: ollama pull).")
    return "\n".join(lines)


async def ask_ollama(user_text: str, snapshot: dict, history: list[tuple[str, str]] | None = None) -> str:
    """SOBRESCRITO: mesmo fluxo original (histórico, streaming, retentativa,
    rodapé de tempo), com duas correções:
      1) pedidos de skill/repositório recebem resposta determinística (mata a
         alucinação de 'instalador' vista no chat);
      2) o system prompt deixa explícito que a regra 'retornar JSON' do bloco
         de extração NÃO vale nesta conversa — o modelo responde sempre em
         texto natural e nunca afirma ter instalado/verificado algo."""
    redirect = _redirect_repo_request(user_text)
    if redirect is not None:
        return redirect
    system = (
        MASTER_EXTRACTION_PROMPT + "\n"
        "Você é o Harness, agente supervisor da AURA. HALem é o usuário e responsável pelas aprovações. Converse em português natural, como um "
        "agente útil e direto. Entenda pedidos informais e não exija comandos exatos. "
        "Se o usuário colar uma especificação longa, trate-a como um único pedido completo: "
        "resuma o objetivo, proponha uma ação consolidada e não faça questionário. Faça no máximo "
        "uma pergunta apenas se faltar um dado indispensável. Nunca invente estado nem diga que "
        "executou algo que não foi executado. Para mudanças, encaminhe para uma única aprovação. "
        "Não repita diagnósticos, listas ou recomendações genéricas. Máximo de 4 linhas.\n"
        "REGRAS INVIOLÁVEIS DESTA CONVERSA: a instrução de 'retornar exclusivamente JSON' do bloco "
        "de extração NÃO se aplica aqui — nesta conversa você SEMPRE responde em texto natural, "
        "nunca em JSON. Você não é um instalador e não tem poder de instalar, verificar, carregar "
        "ou desinstalar nada: nunca emita status/JSON de instalação e nunca afirme ter instalado, "
        "baixado ou verificado modelos, skills ou repositórios — isso seria falso. Se o usuário "
        "pedir instalação de skill/repositório/modelo, responda em texto que o caminho oficial é o "
        "comando 'instalar skill <url>' seguido de CONFIRMAR; modelos Ollama são gerenciados fora "
        "daqui (por exemplo, 'ollama pull')."
    )
    messages = [{"role": "system", "content": system}]
    for user_turn, assistant_turn in (history or [])[-6:]:
        messages.append({"role": "user", "content": user_turn})
        messages.append({"role": "assistant", "content": assistant_turn})
    messages.append({"role": "user", "content": f"CONTEXTO:\n{compact_context(snapshot)}\n\nPEDIDO:\n{user_text}"})
    payload = {
        "model": MODEL,
        "messages": messages,
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
    attempts = 2  # 1 retentativa: o primeiro request após ociosidade pode falhar
    last_error: Exception | None = None
    for attempt in range(attempts):
        chunks = []
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
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(1.5)
    if last_error is not None:
        return f"❌ Falha no Ollama (após retentativa): {last_error}. Verifique se o serviço está rodando em {OLLAMA_URL}."
    result = "".join(chunks).strip() or "NÃO CONFIRMADO"
    elapsed = time.perf_counter() - started
    return f"{result}\n\n[dim]⏱ {elapsed:.1f}s · chamada única · modelo residente[/dim]" if RICH else f"{result}\n[tempo: {elapsed:.1f}s]"


# ---------------------------------------------------------------------------
# 3) CTRL+X ENCERRA O SUPERVISOR (Windows) — Ctrl+C continua valendo
# ---------------------------------------------------------------------------
if os.name == "nt" and MSVCRT_OK:
    def _aura_input(prompt: str = "") -> str:
        """Substitui o input() embutido: leitura tecla a tecla para capturar
        Ctrl+X (que não gera sinal do SO, ao contrário do Ctrl+C). Ctrl+X
        devolve 'sair', então o supervisor encerra pelo mesmo caminho limpo
        do comando 'sair'. Ctrl+C segue levantando KeyboardInterrupt, como
        sempre; Ctrl+Z segue levantando EOFError; Backspace funciona."""
        try:
            sys.stdout.write(str(prompt))
            sys.stdout.flush()
        except Exception:
            pass
        chars: list[str] = []
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars)
            if ch == "\x03":  # Ctrl+C → comportamento original preservado
                raise KeyboardInterrupt
            if ch == "\x1a":  # Ctrl+Z → comportamento original preservado
                raise EOFError
            if ch == "\x18":  # Ctrl+X → encerramento limpo (equivale a 'sair')
                sys.stdout.write("\n")
                sys.stdout.flush()
                if RICH:
                    console.print("[dim]⌨ Ctrl+X — encerrando o supervisor (mesmo efeito de 'sair').[/dim]")
                else:
                    print("Ctrl+X — encerrando o supervisor.")
                return "sair"
            if ch in ("\x08", "\x7f"):  # Backspace
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch in ("\x00", "\xe0"):  # setas/F-keys: consumir e ignorar
                try:
                    msvcrt.getwch()
                except Exception:
                    pass
                continue
            if ch.isprintable():
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    builtins.input = _aura_input
    if RICH:
        console.print("[dim]⌨ Atalhos: Ctrl+X encerra · Ctrl+C continua valendo · 'sair' continua valendo.[/dim]")
    else:
        print("Atalhos: Ctrl+X encerra; Ctrl+C e 'sair' continuam valendo.")