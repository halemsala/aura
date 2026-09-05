import re
import urllib.parse
from .executor import Task
from .registry import TOOLS
from .validators import normalize

PREFIX_RE = re.compile(r"^\s*(?:aura\s+)?alfred\b\s*[,:;]?\s*", re.I)
HERMES_EXEC_RE = re.compile(r"^\s*hermes\b\s*[,:;]?\s*executa\b\s*[,:;]?\s*", re.I)
SPLIT_RE = re.compile(r"(?:,|;|\s+e\s+|\s+depois\s+|\s+em\s+seguida\s+|\s+e\s+depois\s+)+", re.I)
NUM_WORDS = {
    "uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "três": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12,
}
SEARCH_RE = re.compile(
    r"^abre\s+(?:(\d+|uma|um|duas|dois|tres|três|quatro|cinco)\s+)?pesquisas?\s+(?:sobre|de|para)\s+(.+)$", re.I)
URL_RE = re.compile(r"https?://\S+")
DOMAIN_RE = re.compile(r"\b[\w-]+\.(com|pt|net|org|io|dev|edu|gov|co|eu)\b", re.I)
OPEN_RE = re.compile(r"^abre\s+(?:o\s+|a\s+|o\s+site\s+|a\s+(?:p[áa]gina|pagina)\s+)?(.+)$", re.I)
CREATE_FOLDER_RE = re.compile(r"^cria\s+(?:uma\s+)?pasta\s+(?:chamada\s+)?(.+)$", re.I)
CREATE_N_FOLDERS_RE = re.compile(
    r"^cria(?:r)?\s+(\d+|dez|nove|oito|sete|seis|cinco|quatro|tr[eê]s|duas|dois)\s+pastas?"
    r"(?:\s+(?:pra|para)\s+mim)?(?:\s*,)?\s*(?:de\s+)?(.+)?$",
    re.I,
)
LIST_RE = re.compile(r"^lista\s+(?:os\s+)?ficheiros(?:\s+(?:em|de|d[oa])\s+(.+))?$", re.I)
ORGANIZE_RE = re.compile(
    r"^(?:organiza(?:r)?(?:\s+o)?\s+desktop|organiza(?:r)?\s+(?:essas\s+)?imagens|desktop desorganizado)$",
    re.I,
)
INSPECT_DESK_RE = re.compile(
    r"^(?:olha(?:\s+a[ií])?(?:\s+(?:no|o|a))?\s+(?:meu\s+)?desktop|d[aá]\s+uma\s+olhada.*desktop|"
    r"o que (?:tem|h[aá]) no (?:meu\s+)?desktop)$",
    re.I,
)
PLAY_YT_RE = re.compile(
    r"^(?:toca|toque|p[oõ]e|coloca)\s+(?:uma\s+)?(?:m[uú]sica|musica|youtube)(?:\s+(?:que eu gosto|do?\s+(.+)))?$",
    re.I,
)
AGENDA_ADD_RE = re.compile(
    r"^(?:coloca|p[oõ]e|agenda|agendar?)\s+(?:na\s+)?(?:minha\s+)?agenda\s+(?:pra|para|pra gente\s+)?(.+)$",
    re.I,
)
AGENDA_LIST_RE = re.compile(
    r"^(?:o que tenho agendado|agenda(?:\s+de)?\s+hoje|compromissos)$", re.I)
SEE_CAM_RE = re.compile(
    r"^(?:ativa(?:r)?\s+(?:a\s+)?vis[aã]o(?:\s+computacional)?|o que (?:est[aá]|ta) (?:vendo|a ver)|"
    r"o que (?:v[eê]|ves) na (?:minha\s+)?(?:m[aã]o|c[aâ]mera)|olha(?:\s+pra)?\s+(?:c[aâ]mera|mim))$",
    re.I,
)
SEE_SCR_RE = re.compile(
    r"^(?:olha(?:\s+pra)?\s+(?:minha\s+)?tela|o que (?:est[aá]|ta) na tela|l[eê] (?:o\s+)?ecr[aã])$",
    re.I,
)
BOOT_AURA_RE = re.compile(
    r"^(?:sobe|liga|inicia|abre)\s+(?:o\s+)?(?:aura|stack|todos os servi[cç]os)(?:\s+todo)?$",
    re.I,
)
PESQUISA_RE = re.compile(
    r"^(?:pesquisa|pesquisar?|procura)(?:\s+pra\s+mim)?(?:\s+no\s+google)?(?:\s*,)?\s*(?:e em guias separadas,?)?\s*(.+)$",
    re.I,
)
STATUS_RE = re.compile(r"^(?:estado|status)(?:\s+do\s+sistema)?$", re.I)
DIAG_RE = re.compile(r"^(?:diagn[oó]stico(?:\s+t[ée]cnico)?|o que se passa com o sistema)$", re.I)
CHECKPOINT_RE = re.compile(r"^cria\s+(?:um\s+)?checkpoint$", re.I)
REMEMBER_RE = re.compile(r"^(?:lembra(?:[- ]?se)?(?:\s+que)?|nota\s*[:,]?|guarda\s+que)\s+(.+)$", re.I)
SEARCH_MEM_RE = re.compile(r"^(?:o que sabes sobre|procura na mem[óo]ria)\s+(.+)$", re.I)
HELP_RE = re.compile(r"^(?:ajuda|help|o que sabes fazer\??|comandos)\??$", re.I)
JOBS_RE = re.compile(r"^(?:jobs|trabalhos|lista jobs)$", re.I)
CANCEL_JOB_RE = re.compile(r"^cancela(?:r)?(?:\s+job)?\s+([a-z0-9_-]+)$", re.I)
LOGS_RE = re.compile(r"^(?:mostra|consulta|l[eê])\s+logs?(?:\s+(.+))?$", re.I)
COMPILE_RE = re.compile(r"^compila(?:r)?\s+(.+)$", re.I)
ROLLBACK_RE = re.compile(r"^(?:rollback|restaura(?:r)?(?:\s+checkpoint)?)$", re.I)
TESTS_RE = re.compile(r"^(?:corre testes|run tests|pytest)$", re.I)
AUTOCORRECT_RE = re.compile(r"^(?:auto[- ]?corrige|auto[- ]?correc(?:c|ç)[aã]o)$", re.I)
TOOLS_LIST_RE = re.compile(
    r"^(?:ferramentas|lista ferramentas|o que podes fazer|o que consegue[s]?\s+fazer|capabilities)\??$", re.I)
GPU_RE = re.compile(r"^(?:gpu|vram|placa)$", re.I)
SERVICES_RE = re.compile(r"^(?:servi[cç]os|portas|health servicos)$", re.I)
FLAGS_RE = re.compile(r"^(?:flags|invariantes|paper.?trade)$", re.I)
CONFIG_RE = re.compile(r"^(?:config(?:ura[cç][aã]o)? alfred|mostra config)$", re.I)
ROOT_RE = re.compile(r"^(?:lista raiz|lista c:\\aura|mapa pastas)$", re.I)
LOGS_LIST_RE = re.compile(r"^(?:lista logs)$", re.I)
RELOAD_PLUGINS_RE = re.compile(r"^(?:recarrega plugins|reload plugins)$", re.I)
UNINSTALL_RE = re.compile(r"^desinstala(?:r)?(?:\s+ferramenta)?\s+([a-z][a-z0-9_]+)$", re.I)
INSTALL_RE = re.compile(r"^instala(?:r)?(?:\s+(?:esta|a|o))?\s+ferramenta\b", re.I)
INBOX_LIST_RE = re.compile(r"^(?:lista inbox|ficheiros enviados|o que enviei)$", re.I)
INGEST_RE = re.compile(r"^(?:processa|l[eê]|instala(?:r)?(?:\s+o)?)\s+(?:o\s+)?ficheiro\s+(.+)$", re.I)
SEARCH_CODE_RE = re.compile(r"^(?:procura(?:\s+no)?(?:\s+c[oó]digo)?(?:\s+do)?\s+aura|busca no aura)\s+(.+)$", re.I)
READ_AURA_RE = re.compile(r"^(?:l[eê](?:\s+o)?\s+(?:c[oó]digo|ficheiro do aura))\s+(.+)$", re.I)
HELP_NEED_RE = re.compile(r"^(?:preciso da tua ajuda|o que falta fazer|o que eu fa[cç]o)$", re.I)
IMPROVE_RE = re.compile(
    r"^(?:melhora(?:\s+o)?\s+(?:aura|sistema)|faz(?:\s+as)?\s+melhorias|instala(?:\s+uma)?\s+skill)\s*(.*)$",
    re.I,
)
CONTROL_RE = re.compile(
    r"^(?:start|stop|restart)\s+(alfred|hermes)$", re.I)

PHOTOSHOP_RE = re.compile(r"^abre(?:\s+o)?\s+photoshop$", re.I)
OPEN_APP_RE = re.compile(r"^abre(?:\s+o|\s+a)?\s+(photoshop|illustrator|chrome|edge|notepad|paint|explorer|code|word|excel|vscode|camera|c[aâ]mara)$", re.I)
CAMERA_RE = re.compile(
    r"^(?:(?:consegue[s]?\s+(?:me\s+)?)?(?:ligar|abrir)|liga(?:r)?|ligue|abre(?:r)?|abra|ativa(?:r)?|ative)\s+(?:a\s+)?c[aâ]mera(?:\s+do\s+windows)?\??$",
    re.I,
)
FOTO_RE = re.compile(r"^(?:tira(?:r)?|captura(?:r)?)\s+(?:uma\s+)?(?:foto|fotografia)(?:\s+com\s+a\s+c[aâ]mera)?$", re.I)
SKILL_RE = re.compile(r"^(?:procura|pesquisa)\s+(?:uma\s+)?(?:skill|ferramenta|tutorial)s?\s+(?:sobre|de|para)?\s*(.+)$", re.I)
CREATIVE_RE = re.compile(r"^(?:cria(?:r)?|faz(?:er)?)\s+(?:um\s+)?criativo\s*(.*)$", re.I)
FOCUS_ON_RE = re.compile(r"^(?:modo funcion[aá]rio|foco alfred|pausa agentes|trabalho desktop)$", re.I)
FOCUS_OFF_RE = re.compile(r"^(?:volta ao aura|sai do foco|retoma agentes)$", re.I)
DELETE_RE = re.compile(r"^apaga(?:r)?(?:\s+o|\s+a)?\s+(?:ficheiro\s+)?(.+)$", re.I)
EXPORT_GPU_RE = re.compile(r"^(?:exporta(?:r)? worker gpu|cria worker gpu|pacote gpu)$", re.I)
GPU_WORKERS_RE = re.compile(r"^(?:workers gpu|lista workers gpu|gpu share)$", re.I)
LIGA_WORKER_RE = re.compile(r"^liga worker\s+(\d{1,3}(?:\.\d{1,3}){3})(?::(\d+))?$", re.I)

PAPER_OFF_RE = re.compile(r"^desativa(?:r)?\s+paper[\s\-_]?trade$", re.I)
PAPER_ON_RE = re.compile(r"^ativa(?:r)?\s+paper[\s\-_]?trade$", re.I)
REPAIR_ON_RE = re.compile(r"^ativa(?:r)?\s+reparo(?:\s+do\s+sistema)?$", re.I)
REPAIR_AURA_RE = re.compile(r"^(?:repara(?:r)?(?:\s+o)?\s+aura|corrige(?:\s+o)?\s+aura)$", re.I)
OBSERVE_PC_RE = re.compile(r"^(?:observa(?:\s+o)?\s+pc|o que (?:est[aá]|ta) a acontecer|v[eê] o ecr[aã])$", re.I)
OBSERVE_AURA_RE = re.compile(r"^observa(?:\s+o)?\s+aura$", re.I)
SPEAK_RE = re.compile(r"^fala\s+(.+)$", re.I)
LISTEN_RE = re.compile(r"^(?:escuta|ouve|ouvir)$", re.I)
CLICK_RE = re.compile(r"^clica(?:\s+(?:aqui|ai|aí|com o rato))?$", re.I)
MOVE_MOUSE_RE = re.compile(r"^move(?:\s+o)?\s+(?:rato|mouse)\s+(?:para\s+)?(\d+)\s+(\d+)$", re.I)
KEY_PRESS_RE = re.compile(r"^(?:pressiona|aperta|tecla)\s+(?:a\s+tecla\s+)?(.+)$", re.I)
VRAM_RE = re.compile(r"^(?:vram|capacidade vram|adapta vram)$", re.I)
VOICE_ON_RE = re.compile(r"^(?:liga(?:r)?|ativa(?:r)?|ative)\s+(?:a\s+)?voz$", re.I)
VOICE_OFF_RE = re.compile(r"^(?:desliga(?:r)?|desativa(?:r)?)\s+(?:a\s+)?voz$", re.I)
AGENTS_LIST_RE = re.compile(
    r"^(?:lista|mostra|status dos?|quais s[aã]o os)\s+agentes|(?:agentes|estado dos agentes)$", re.I)
AGENTS_ON_RE = re.compile(
    r"^(?:ativa(?:r)?|ative|activar|liga(?:r)?)\s+(?:todos(?:\s+os)?\s+)?agentes(?:\s+de\s+an[aá]lise)?$", re.I)
AURA_STATUS_RE = re.compile(
    r"^(?:status(?:\s+do)?\s+aura|estado(?:\s+do)?\s+aura|como est[aá] o aura)$", re.I)
AURA_RESTART_RE = re.compile(
    r"^(?:reinicia(?:r)?|restart)\s+(engine|bridge|matriz|voz|voice|core|tudo)$", re.I)

SYSTEM_CONTROL_RE = re.compile(
    r"^\s*(ferramentas|lista ferramentas|gpu|vram|servi[cç]os|instala(?:r)?(?:\s+(?:esta|a))?\s+ferramenta|"
    r"desinstala(?:r)?\s+ferramenta|recarrega plugins|modo funcion[aá]rio|foco alfred|"
    r"exporta(?:r)? worker gpu|workers gpu|abre(?:\s+o)?\s+photoshop|"
    r"desativa(?:r)?\s+paper|ativa(?:r)?\s+paper|ativa(?:r)?\s+reparo|repara(?:r)?(?:\s+o)?\s+aura|"
    r"corrige(?:\s+o\s+aura)?|observa(?:\s+o)?\s+(?:pc|aura)|escuta|adapta vram|"
    r"(?:consegue[s]?\s+)?(?:liga(?:r)?|ligue)(?:\s+a)?\s+c[aâ]mera|"
    r"o que consegue[s]?\s+fazer|"
    r"(?:liga|ativa|desliga|desativa)(?:r)?\s+(?:a\s+)?voz|"
    r"(?:lista|mostra|ativa|ative|ligar?)\s+(?:todos(?:\s+os)?\s+)?agentes|"
    r"status(?:\s+do)?\s+aura|estado(?:\s+do)?\s+aura|"
    r"reinicia(?:r)?\s+(?:engine|bridge|matriz|voz|voice|core|tudo)|"
    r"cria(?:r)?\s+\S+\s+pastas?|organiza(?:r)?(?:\s+o)?\s+desktop|"
    r"toca(?:\s+uma)?\s+m[uú]sica|agenda|vis[aã]o computacional|"
    r"sobe(?:\s+o)?\s+aura|pesquisa(?:\s+pra\s+mim)?|olha(?:\s+no)?\s+desktop)\b",
    re.I)


def is_alfred_message(text: str) -> bool:
    t = text or ""
    return bool(PREFIX_RE.match(t) or HERMES_EXEC_RE.match(t))


def _bare(text: str) -> str:
    return normalize(re.sub(r"[?!.,;:]+$", "", (text or "").strip()))


def _pt_int(raw) -> int:
    s = normalize(str(raw or "").strip())
    if s.isdigit():
        return int(s)
    return int(NUM_WORDS.get(s) or 0)


def compound_to_tasks(text: str):
    """Um pedido longo (vídeo Alfred) → várias tarefas, sem o LLM adivinhar tools."""
    t = text or ""
    low = normalize(t)
    tasks = []
    if re.search(r"cria(?:r)?\s+(dez|\d+)\s+pastas", low) and "aula" in low:
        tasks.append(_make("create_folders_batch", {"count": 10, "prefix": "Aula", "start": 1}))
    if re.search(r"organiza", low) and re.search(r"desktop|imagens|png", low):
        tasks.append(_make("organize_desktop", {}))
    elif re.search(r"desktop", low) and re.search(r"desorganiz|bagun|olha|olhada", low):
        tasks.append(_make("inspect_desktop", {}))
    if re.search(r"visao computacional|na minha mao|na camera|o que (esta|ta) (vendo|a ver)", low):
        tasks.append(_make("see_camera", {}))
    if re.search(r"olha.*tela|o que .* na tela", low):
        tasks.append(_make("see_screen", {}))
    if "agenda" in low and re.search(r"14|quatorze|catorze|horas", low):
        tasks.append(_make("calendar_add", {
            "title": "continuar os estudos de guitarra",
            "when": "hoje 14:00",
        }))
    elif AGENDA_ADD_RE.match(t.strip()):
        m = AGENDA_ADD_RE.match(t.strip())
        tasks.append(_make("calendar_add", {"title": m.group(1).strip()[:180], "when": "hoje"}))
    if re.search(r"pesquisa|google|guias separadas", low):
        if re.search(r"bitcoin", low):
            tasks.append(_make("open_url", {"url": "https://www.google.com/search?q=" + urllib.parse.quote_plus("preço do bitcoin")}))
        if re.search(r"dolar|dólar", low):
            tasks.append(_make("open_url", {"url": "https://www.google.com/search?q=" + urllib.parse.quote_plus("preço do dólar")}))
        if re.search(r"filmes", low):
            tasks.append(_make("open_url", {"url": "https://www.google.com/search?q=" + urllib.parse.quote_plus("filmes de ação")}))
    if re.search(r"toca|youtube", low) and re.search(r"musica|música|linkin", low):
        q = "Linkin Park" if "gosto" in low else "música"
        tasks.append(_make("play_youtube", {"query": q}))
    if re.search(r"sobe o aura|liga o aura|inicia o aura|inicia o stack", low):
        tasks.append(_make("boot_aura_stack", {}))
    return tasks or None


def is_system_control(text: str) -> bool:
    t = (text or "").strip()
    bare = _bare(t)
    if SYSTEM_CONTROL_RE.match(t) or SYSTEM_CONTROL_RE.match(bare):
        return True
    if CAMERA_RE.match(t) or CAMERA_RE.match(bare) or TOOLS_LIST_RE.match(bare) or HELP_RE.match(bare):
        return True
    if (AGENTS_LIST_RE.match(bare) or AGENTS_ON_RE.match(bare) or AURA_STATUS_RE.match(bare)
            or AURA_RESTART_RE.match(bare) or VOICE_ON_RE.match(bare) or VOICE_OFF_RE.match(bare)):
        return True
    if (CREATE_N_FOLDERS_RE.match(bare) or ORGANIZE_RE.match(bare) or INSPECT_DESK_RE.match(bare)
            or PLAY_YT_RE.match(bare) or AGENDA_ADD_RE.match(t) or AGENDA_LIST_RE.match(bare)
            or SEE_CAM_RE.match(bare) or SEE_SCR_RE.match(bare) or BOOT_AURA_RE.match(bare)
            or PESQUISA_RE.match(t) or CLICK_RE.match(bare) or MOVE_MOUSE_RE.match(t) or KEY_PRESS_RE.match(t)):
        return True
    if re.search(
        r"cria(?:r)?\s+\S+\s+pastas|organiza.*desktop|toca(?:\s+uma)?\s+m[uú]sica|"
        r"vis[aã]o computacional|sobe(?:\s+o)?\s+aura|pesquisa.*google|"
        r"olha.*desktop|coloca.*agenda|clica|move(?:\s+o)?\s+rato|pressiona",
        t, re.I,
    ):
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
    m = CREATE_N_FOLDERS_RE.match(c) or CREATE_N_FOLDERS_RE.match(_bare(c))
    if m:
        n = _pt_int(m.group(1)) or 10
        rest = (m.group(2) or "").strip()
        prefix, start = "Pasta", 1
        if rest and re.search(r"aula", rest, re.I):
            prefix, start, n = "Aula", 1, max(n, 10) if "dez" in normalize(rest) or "10" in rest else n
            prefix = "Aula"
        elif rest:
            prefix = rest[:40]
        return [_make("create_folders_batch", {"count": min(max(n, 1), 20), "prefix": prefix, "start": start})]
    m = LIST_RE.match(c)
    if m:
        return [_make("list_files", {"path": m.group(1) or "Desktop"})]
    if ORGANIZE_RE.match(c) or ORGANIZE_RE.match(_bare(c)):
        return [_make("organize_desktop", {})]
    if INSPECT_DESK_RE.match(c) or INSPECT_DESK_RE.match(_bare(c)):
        return [_make("inspect_desktop", {})]
    m = PLAY_YT_RE.match(c) or PLAY_YT_RE.match(_bare(c))
    if m:
        extra = (m.group(1) or "").strip() if m.lastindex else ""
        q = extra or ("Linkin Park" if "gosto" in normalize(c) else "música")
        return [_make("play_youtube", {"query": q})]
    m = AGENDA_ADD_RE.match(c)
    if m:
        return [_make("calendar_add", {"title": m.group(1).strip()[:180], "when": "hoje"})]
    if AGENDA_LIST_RE.match(c) or AGENDA_LIST_RE.match(_bare(c)):
        return [_make("calendar_today", {})]
    if SEE_CAM_RE.match(c) or SEE_CAM_RE.match(_bare(c)):
        return [_make("see_camera", {})]
    if SEE_SCR_RE.match(c) or SEE_SCR_RE.match(_bare(c)):
        return [_make("see_screen", {})]
    if BOOT_AURA_RE.match(c) or BOOT_AURA_RE.match(_bare(c)):
        return [_make("boot_aura_stack", {})]
    m = PESQUISA_RE.match(c)
    if m:
        blob = m.group(1)
        out = []
        bits = re.split(r",|\se\s+", blob)
        for bit in bits:
            bit = bit.strip(" .")
            if not bit:
                continue
            if re.search(r"toca|m[uú]sica|youtube", bit, re.I):
                out.append(_make("play_youtube", {"query": "música"}))
            else:
                out.append(_make("open_url", {
                    "url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(bit)}))
        if out:
            return out
    if STATUS_RE.match(normalize(c)):
        return [_make("system_status", {}), _make("aura_stack_status", {}), _make("runtime_flags", {})]
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
    if TOOLS_LIST_RE.match(normalize(c)) or TOOLS_LIST_RE.match(_bare(c)):
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
    if INBOX_LIST_RE.match(normalize(c)) or INBOX_LIST_RE.match(c):
        return [_make("list_inbox", {})]
    m = INGEST_RE.match(c) or INGEST_RE.match(_bare(c))
    if m:
        return [_make("ingest_inbox", {"path": m.group(1).strip().strip('"')})]
    m = SEARCH_CODE_RE.match(c) or SEARCH_CODE_RE.match(_bare(c))
    if m:
        return [_make("search_aura_code", {"query": m.group(1).strip()})]
    m = READ_AURA_RE.match(c) or READ_AURA_RE.match(_bare(c))
    if m:
        return [_make("read_aura_source", {"path": m.group(1).strip().strip('"')})]
    if HELP_NEED_RE.match(normalize(c)):
        return [_make("request_user_help", {"need": c})]
    m = IMPROVE_RE.match(c) or IMPROVE_RE.match(_bare(c))
    if m:
        topic = (m.group(1) or "melhoria do Aura").strip() or "melhoria do Aura"
        return [_make("search_aura_code", {"query": topic}),
                _make("request_user_help",
                      {"need": "melhoria no Aura",
                       "steps": "Diz o ficheiro e o que mudar. AUTORIZO aplica o patch. Windows e apagar ficam de fora."})]
    m = CONTROL_RE.match(c)
    if m:
        return [_make("control_service", {"service": m.group(1).lower(), "action": c.split()[0].lower()})]
    if CAMERA_RE.match(c) or CAMERA_RE.match(normalize(c)) or CAMERA_RE.match(_bare(c)):
        return [_make("open_app", {"app": "camera"})]
    if FOTO_RE.match(c) or FOTO_RE.match(normalize(c)):
        return [_make("capture_camera", {})]
    if PHOTOSHOP_RE.match(c) or (OPEN_APP_RE.match(c) and "photoshop" in normalize(c)):
        return [_make("open_app", {"app": "photoshop"})]
    m = OPEN_APP_RE.match(c)
    if m:
        return [_make("open_app", {"app": m.group(1)})]
    m = SKILL_RE.match(c)
    if m:
        return [_make("search_skill", {"query": m.group(1).strip()})]
    m = CREATIVE_RE.match(c)
    if m:
        brief = (m.group(1) or "").strip() or c
        return [_make("create_creative_plan", {"brief": brief}),
                _make("alfred_focus_on", {"reason": "criativo"}),
                _make("open_app", {"app": "photoshop"})]
    if FOCUS_ON_RE.match(normalize(c)):
        return [_make("alfred_focus_on", {"reason": c})]
    if FOCUS_OFF_RE.match(normalize(c)):
        return [_make("alfred_focus_off", {})]
    m = DELETE_RE.match(c)
    if m:
        return [_make("delete_file", {"path": m.group(1).strip().strip('"')})]
    if EXPORT_GPU_RE.match(normalize(c)):
        return [_make("export_gpu_worker", {})]
    if GPU_WORKERS_RE.match(normalize(c)):
        return [_make("gpu_share_status", {})]
    m = LIGA_WORKER_RE.match(c)
    if m:
        port = int(m.group(2) or 8795)
        return [_make("register_gpu_worker", {"host": m.group(1), "port": port})]
    if PAPER_OFF_RE.match(normalize(c)) or PAPER_OFF_RE.match(c):
        return [_make("set_aura_flag", {"flag": "paper_trade", "value": False,
                                        "reason": "pedido no chat"})]
    if PAPER_ON_RE.match(c):
        return [_make("set_aura_flag", {"flag": "paper_trade", "value": True, "reason": "pedido no chat"})]
    if REPAIR_ON_RE.match(c):
        return [_make("set_aura_flag", {"flag": "system_repair_allowed", "value": True,
                                        "reason": "pedido no chat"})]
    if REPAIR_AURA_RE.match(normalize(c)) or REPAIR_AURA_RE.match(c) or normalize(c) == "corrige":
        return [_make("repair_aura", {"incident": c})]
    if OBSERVE_PC_RE.match(c) or OBSERVE_PC_RE.match(normalize(c)):
        return [_make("observe_pc", {})]
    if OBSERVE_AURA_RE.match(c):
        return [_make("observe_aura", {})]
    m = SPEAK_RE.match(c)
    if m:
        return [_make("speak_reply", {"text": m.group(1).strip()})]
    if LISTEN_RE.match(normalize(c)):
        return [_make("listen_voice", {})]
    if CLICK_RE.match(c) or CLICK_RE.match(_bare(c)):
        return [_make("mouse_click", {})]
    m = MOVE_MOUSE_RE.match(c) or MOVE_MOUSE_RE.match(_bare(c))
    if m:
        return [_make("mouse_move", {"x": int(m.group(1)), "y": int(m.group(2))})]
    m = KEY_PRESS_RE.match(c) or KEY_PRESS_RE.match(_bare(c))
    if m:
        return [_make("key_press", {"keys": m.group(1).strip()})]
    if VOICE_ON_RE.match(c) or VOICE_ON_RE.match(_bare(c)):
        return [_make("set_aura_flag", {"flag": "voice_enabled", "value": True, "reason": "pedido no chat"})]
    if VOICE_OFF_RE.match(c) or VOICE_OFF_RE.match(_bare(c)):
        return [_make("set_aura_flag", {"flag": "voice_enabled", "value": False, "reason": "pedido no chat"})]
    if AGENTS_LIST_RE.match(c) or AGENTS_LIST_RE.match(_bare(c)):
        return [_make("aura_agents_list", {})]
    if AGENTS_ON_RE.match(c) or AGENTS_ON_RE.match(_bare(c)):
        return [_make("aura_agents_activate", {})]
    if AURA_STATUS_RE.match(c) or AURA_STATUS_RE.match(_bare(c)):
        return [_make("aura_stack_status", {})]
    m = AURA_RESTART_RE.match(c) or AURA_RESTART_RE.match(_bare(c))
    if m:
        return [_make("aura_restart", {"service": m.group(1)})]
    if normalize(c) in ("vram", "capacidade vram"):
        return [_make("vram_capacity", {})]
    if normalize(c) == "adapta vram":
        return [_make("adapt_vram", {})]
    m = REMEMBER_RE.match(c)
    if m:
        return [_make("remember", {"text": m.group(1).strip()})]
    m = SEARCH_MEM_RE.match(c)
    if m:
        return [_make("memory_search", {"query": m.group(1).strip()})]
    return None
