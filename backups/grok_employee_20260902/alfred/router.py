import re
import urllib.parse
from .executor import Task
from .registry import TOOLS
from .validators import normalize

PREFIX_RE = re.compile(r"^\s*(?:aura\s+)?alfred\b\s*[,:;]?\s*", re.I)
HERMES_EXEC_RE = re.compile(r"^\s*hermes\b\s*[,:;]?\s*executa\b\s*[,:;]?\s*", re.I)
SPLIT_RE = re.compile(r"(?:,|;|\s+e\s+|\s+depois\s+|\s+em\s+seguida\s+|\s+e\s+depois\s+)+", re.I)
NUM_WORDS = {"uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5}
SEARCH_RE = re.compile(
    r"^abre\s+(?:(\d+|uma|um|duas|dois|tres|três|quatro|cinco)\s+)?pesquisas?\s+(?:sobre|de|para)\s+(.+)$", re.I)
URL_RE = re.compile(r"https?://\S+")
DOMAIN_RE = re.compile(r"\b[\w-]+\.(com|pt|net|org|io|dev|edu|gov|co|eu)\b", re.I)
OPEN_RE = re.compile(r"^abre\s+(?:o\s+|a\s+|o\s+site\s+|a\s+(?:p[áa]gina|pagina)\s+)?(.+)$", re.I)
CREATE_FOLDER_RE = re.compile(r"^cria\s+(?:uma\s+)?pasta\s+(?:chamada\s+)?(.+)$", re.I)
LIST_RE = re.compile(r"^lista\s+(?:os\s+)?ficheiros(?:\s+(?:em|de|d[oa])\s+(.+))?$", re.I)
ORGANIZE_RE = re.compile(r"^organiza\s+(?:o\s+)?desktop$", re.I)
STATUS_RE = re.compile(r"^(?:estado|status)(?:\s+do\s+sistema)?$", re.I)
DIAG_RE = re.compile(r"^(?:diagn[oó]stico(?:\s+t[ée]cnico)?|o que se passa com o sistema)$", re.I)
CHECKPOINT_RE = re.compile(r"^cria\s+(?:um\s+)?checkpoint$", re.I)
REMEMBER_RE = re.compile(r"^(?:lembra(?:[- ]?se)?(?:\s+que)?|nota\s*[:,]?|guarda\s+que)\s+(.+)$", re.I)
SEARCH_MEM_RE = re.compile(r"^(?:o que sabes sobre|procura na mem[óo]ria)\s+(.+)$", re.I)
HELP_RE = re.compile(r"^(?:ajuda|help|o que sabes fazer\??|comandos)?$", re.I)
JOBS_RE = re.compile(r"^(?:jobs|trabalhos|lista jobs)$", re.I)
CANCEL_JOB_RE = re.compile(r"^cancela(?:r)?(?:\s+job)?\s+([a-z0-9_-]+)$", re.I)
LOGS_RE = re.compile(r"^(?:mostra|consulta|l[eê])\s+logs?(?:\s+(.+))?$", re.I)
COMPILE_RE = re.compile(r"^compila(?:r)?\s+(.+)$", re.I)
ROLLBACK_RE = re.compile(r"^(?:rollback|restaura(?:r)?(?:\s+checkpoint)?)$", re.I)
TESTS_RE = re.compile(r"^(?:corre testes|run tests|pytest)$", re.I)
AUTOCORRECT_RE = re.compile(r"^(?:auto[- ]?corrige|auto[- ]?correc(?:c|ç)[aã]o)$", re.I)
TOOLS_LIST_RE = re.compile(r"^(?:ferramentas|lista ferramentas|o que podes fazer|capabilities)$", re.I)
GPU_RE = re.compile(r"^(?:gpu|vram|placa)$", re.I)
SERVICES_RE = re.compile(r"^(?:servi[cç]os|portas|health servicos)$", re.I)
FLAGS_RE = re.compile(r"^(?:flags|invariantes|paper.?trade)$", re.I)
CONFIG_RE = re.compile(r"^(?:config(?:ura[cç][aã]o)? alfred|mostra config)$", re.I)
ROOT_RE = re.compile(r"^(?:lista raiz|lista c:\\aura|mapa pastas)$", re.I)
LOGS_LIST_RE = re.compile(r"^(?:lista logs)$", re.I)
RELOAD_PLUGINS_RE = re.compile(r"^(?:recarrega plugins|reload plugins)$", re.I)
UNINSTALL_RE = re.compile(r"^desinstala(?:r)?(?:\s+ferramenta)?\s+([a-z][a-z0-9_]+)$", re.I)
INSTALL_RE = re.compile(r"^instala(?:r)?(?:\s+(?:esta|a|o))?\s+ferramenta\b", re.I)
CONTROL_RE = re.compile(
    r"^(?:start|stop|restart)\s+(alfred|hermes)$", re.I)

SYSTEM_CONTROL_RE = re.compile(
    r"^\s*(ferramentas|lista ferramentas|gpu|vram|servi[cç]os|instala(?:r)?(?:\s+(?:esta|a))?\s+ferramenta|"
    r"desinstala(?:r)?\s+ferramenta|recarrega plugins)\b",
    re.I)


def is_alfred_message(text: str) -> bool:
    t = text or ""
    return bool(PREFIX_RE.match(t) or HERMES_EXEC_RE.match(t))


def is_system_control(text: str) -> bool:
    t = (text or "").strip()
    if SYSTEM_CONTROL_RE.match(t):
        return True
    try:
        from .tool_review import is_install_intent
        return is_install_intent(t)
    except Exception:  # noqa: BLE001
        return False


def strip_prefix(text: str) -> str:
    t = text or ""
    t = PREFIX_RE.sub("", t, count=1)
    t = HERMES_EXEC_RE.sub("", t, count=1)
    return t.strip()


def is_help(text: str) -> bool:
    return bool(HELP_RE.match(normalize(text)))


def decompose(text: str, max_tasks: int = 8) -> list:
    parts = [p.strip() for p in SPLIT_RE.split(text or "") if p.strip()]
    return parts[:max_tasks]


def _make(tool: str, args: dict) -> Task:
    spec = TOOLS[tool]
    return Task(id="", tool=tool, arguments=args, risk=spec.risk, mutating=spec.mutating)


def _even_split(words: list, n: int) -> list:
    k, r = divmod(len(words), n)
    out, i = [], 0
    for j in range(n):
        size = k + (1 if j < r else 0)
        out.append(" ".join(words[i:i + size]))
        i += size
    return [w for w in out if w]


def generate_search_urls(topic: str, count: int) -> list:
    topic = (topic or "").strip()[:200]
    count = max(1, min(count, 5))
    base = "https://www.google.com/search?q="
    words = topic.split()
    if len(words) >= count:
        return [base + urllib.parse.quote_plus(q) for q in _even_split(words, count)]
    extras = ["", " tutorial", " exemplos", " ferramentas", " guia"]
    return [base + urllib.parse.quote_plus((topic + extras[i]).strip()) for i in range(count)]


def chunk_to_tasks(chunk: str):
    """Interpretação determinística. Devolve lista de Task ou None."""
    c = chunk.strip()
    if not c:
        return None
    m = SEARCH_RE.match(c)
    if m:
        n_raw = m.group(1)
        n = NUM_WORDS.get(normalize(n_raw), int(n_raw)) if n_raw and n_raw.isdigit() else \
            NUM_WORDS.get(normalize(n_raw or ""), 1)
        return [_make("open_url", {"url": u}) for u in generate_search_urls(m.group(2), n)]
    m = OPEN_RE.match(c)
    if m:
        target = m.group(1).strip().rstrip(".")
        if URL_RE.match(target):
            return [_make("open_url", {"url": target})]
        if DOMAIN_RE.search(target):
            return [_make("open_url", {"url": "https://" + target})]
        return [_make("open_url", {"url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(target)})]
    m = CREATE_FOLDER_RE.match(c)
    if m:
        return [_make("create_folder", {"name": m.group(1).strip()[:80]})]
    m = LIST_RE.match(c)
    if m:
        return [_make("list_files", {"path": m.group(1) or "Desktop"})]
    if ORGANIZE_RE.match(c):
        return [_make("organize_desktop", {})]
    if STATUS_RE.match(normalize(c)):
        return [_make("system_status", {})]
    if DIAG_RE.match(normalize(c)):
        return [_make("technical_diagnose", {})]
    if CHECKPOINT_RE.match(normalize(c)):
        return [_make("create_checkpoint", {})]
    if JOBS_RE.match(normalize(c)):
        return [_make("list_jobs", {})]
    m = CANCEL_JOB_RE.match(c)
    if m:
        return [_make("cancel_job", {"job_id": m.group(1).strip()})]
    m = LOGS_RE.match(c)
    if m:
        return [_make("read_recent_log", {"file": (m.group(1) or "alfred.log").strip(), "lines": 40})]
    m = COMPILE_RE.match(c)
    if m:
        return [_make("run_python_compile", {"path": m.group(1).strip()})]
    if ROLLBACK_RE.match(normalize(c)):
        return [_make("rollback_last", {})]
    if TESTS_RE.match(normalize(c)):
        return [_make("run_project_tests", {})]
    if AUTOCORRECT_RE.match(normalize(c)):
        return [_make("auto_correct", {"incident": c})]
    if TOOLS_LIST_RE.match(normalize(c)):
        return [_make("list_tools", {})]
    if GPU_RE.match(normalize(c)):
        return [_make("gpu_report", {})]
    if SERVICES_RE.match(normalize(c)):
        return [_make("services_status", {})]
    if FLAGS_RE.match(normalize(c)):
        return [_make("runtime_flags", {})]
    if CONFIG_RE.match(normalize(c)):
        return [_make("read_alfred_config", {})]
    if ROOT_RE.match(c) or normalize(c) == "lista raiz":
        return [_make("list_aura_root", {})]
    if LOGS_LIST_RE.match(normalize(c)):
        return [_make("list_recent_logs", {})]
    if RELOAD_PLUGINS_RE.match(normalize(c)):
        return [_make("reload_plugins", {})]
    m = UNINSTALL_RE.match(c)
    if m:
        return [_make("uninstall_tool", {"name": m.group(1).strip()})]
    m = CONTROL_RE.match(c)
    if m:
        return [_make("control_service", {"service": m.group(1).lower(), "action": c.split()[0].lower()})]
    m = REMEMBER_RE.match(c)
    if m:
        return [_make("remember", {"text": m.group(1).strip()})]
    m = SEARCH_MEM_RE.match(c)
    if m:
        return [_make("memory_search", {"query": m.group(1).strip()})]
    return None
