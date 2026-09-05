import hashlib, json, re, uuid
from .config import get_config
from .executor import Task, Plan, plan_to_dict  # noqa: F401 (plan_to_dict re-exportado)
from .registry import TOOLS
from .router import URL_RE, chunk_to_tasks, compound_to_tasks, decompose
from .util import jsonable
from .validators import ValidationError


class PlanningError(ValueError):
    pass


def _tools_prompt() -> str:
    from .registry import capabilities
    lines = ["És o planeador do Alfred (Aura/Hermes). Converte o pedido em tarefas.",
             "Responde APENAS com JSON válido: {\"tasks\":[{\"tool\":\"nome\",\"arguments\":{...}}]}",
             "Ferramentas registadas:"]
    for t in capabilities():
        lines.append(f"- {t['name']} (risk={t['risk']}, mutating={t['mutating']}, origin={t.get('origin')}) {t.get('summary','')}")
    lines.append("Regras: máximo 8 tarefas; nunca inventes ferramentas; nunca executes; "
                 "não uses install_tool sem código já revisto; para URLs usa open_url.")
    return "\n".join(lines)


TOOLS_PROMPT = None  # preenchido dinamicamente — ver _tools_prompt()

OPEN_INTENT_RE = re.compile(r"(?i)\b(abre|abrir|open|pesquis|procura|busca|site|p[áa]gina)\b")


def _extract_json(s: str) -> dict:
    m = re.search(r"\{.*\}", s or "", re.S)
    if not m:
        raise PlanningError("planeador LLM não devolveu JSON")
    return json.loads(m.group(0))


def _validated_task(raw: dict, source_text: str, is_llm: bool):
    if not isinstance(raw, dict):
        return None, "tarefa não é um objecto"
    tool = str(raw.get("tool", ""))
    spec = TOOLS.get(tool)
    if spec is None:
        return None, f"ferramenta desconhecida: {tool}"
    if is_llm and tool == "open_url" and not (OPEN_INTENT_RE.search(source_text) or URL_RE.search(source_text)):
        return None, "open_url bloqueado: o pedido não indica intenção de abrir páginas"
    try:
        args = jsonable(spec.validate(raw.get("arguments") or {}))
    except ValidationError as e:
        return None, f"argumentos inválidos para {tool}: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"validação de {tool} falhou: {e}"
    return Task(id="", tool=tool, arguments=args, risk=spec.risk, mutating=spec.mutating,
                timeout=float(get_config().get("task_timeout_s", 30)),
                retry_policy={"max_retries": int(get_config().get("max_retries", 2)), "backoff_s": 0.4}), None


def _llm_plan(unresolved: list, source_text: str, client) -> list:
    ask = " | ".join(unresolved)
    try:
        out = client.chat(
            [{"role": "system", "content": _tools_prompt()},
             {"role": "user", "content": f"Pedido: {ask}"}],
            temperature=0.1, num_predict=768)
    except Exception as e:  # OllamaUnavailable / OllamaError
        raise PlanningError(f"planeamento por LLM indisponível: {e}") from e
    try:
        data = _extract_json(out)
    except (json.JSONDecodeError, PlanningError) as e:
        raise PlanningError(f"planeador LLM devolveu formato inválido: {e}") from e
    tasks, reasons = [], []
    for raw in (data.get("tasks") or [])[: get_config()["max_tasks"]]:
        t, why = _validated_task(raw, source_text, is_llm=True)
        (tasks.append(t) if t else reasons.append(why))
    return tasks


def plan_from_message(message: str, client=None) -> Plan:
    cfg = get_config()
    chunks = decompose(message, cfg["max_tasks"])
    if not chunks:
        raise PlanningError("pedido vazio")
    tasks, unresolved = [], []
    combo = compound_to_tasks(message.strip())
    whole = chunk_to_tasks(message.strip())
    if combo and len(combo) >= 2:
        tasks.extend(combo)
    elif whole:
        tasks.extend(whole)
    elif combo:
        tasks.extend(combo)
    else:
        for c in chunks:
            got = chunk_to_tasks(c)
            (tasks.extend(got) if got else unresolved.append(c))
    if unresolved and client is not None:
        tasks.extend(_llm_plan(unresolved, message, client))
    if unresolved and not tasks and client is None:
        raise PlanningError(
            "não percebi o pedido (e o LLM local está offline). Exemplos: 'abre três pesquisas sobre X', "
            "'cria pasta X', 'lista ficheiros', 'organiza desktop', 'estado', 'diagnóstico', 'ajuda'")
    # dedupe + validação final por código (mesmo para tarefas determinísticas)
    seen, uniq, rejected = set(), [], []
    for t in tasks:
        key = (t.tool, json.dumps(t.arguments, sort_keys=True, ensure_ascii=False))
        if key in seen:
            continue
        spec = TOOLS[t.tool]
        try:
            t.arguments = jsonable(spec.validate(t.arguments))
        except ValidationError as e:
            rejected.append(f"{t.tool}: {e}")
            continue
        seen.add(key)
        uniq.append(t)
    tasks = uniq[: cfg["max_tasks"]]
    if not tasks:
        raise PlanningError("nenhuma tarefa válida: " + ("; ".join(rejected) or "pedido irreconhecível"))
    for i, t in enumerate(tasks, 1):
        t.id = f"task-{i}"
        t.risk = TOOLS[t.tool].risk
        t.mutating = TOOLS[t.tool].mutating
        if not t.timeout:
            t.timeout = float(cfg.get("task_timeout_s", 30))
        if not t.retry_policy:
            t.retry_policy = {"max_retries": int(cfg.get("max_retries", 2)), "backoff_s": 0.4}
    sensitive = any(TOOLS[t.tool].sensitive for t in tasks)
    n_mutating = sum(1 for t in tasks if TOOLS[t.tool].mutating)
    requires = sensitive or n_mutating > 0
    intent = "search_multi" if (len(tasks) > 1 and all(t.tool == "open_url" for t in tasks)) else \
             ("single_task" if len(tasks) == 1 else "multi_task")
    content_hash = hashlib.sha256(
        json.dumps([(t.tool, t.arguments) for t in tasks], sort_keys=True).encode()).hexdigest()[:16]
    return Plan(request_id=uuid.uuid4().hex[:12], intent=intent, requires_confirmation=requires,
                tasks=tasks, created_from=message, content_hash=content_hash)


def plan_from_dict(d: dict) -> Plan:
    """Reconstrói um plano vindo da API /execute, revalidando tudo por código."""
    if not isinstance(d, dict) or not isinstance(d.get("tasks"), list):
        raise PlanningError("plano inválido")
    tasks, rejected = [], []
    for raw in d["tasks"][: get_config()["max_tasks"]]:
        t, why = _validated_task(raw, d.get("source_message") or json.dumps(raw, ensure_ascii=False), is_llm=False)
        (tasks.append(t) if t else rejected.append(why or "?"))
    if not tasks:
        raise PlanningError("plano sem tarefas válidas: " + "; ".join(rejected))
    for i, t in enumerate(tasks, 1):
        t.id = f"task-{i}"
    sensitive = any(TOOLS[t.tool].sensitive for t in tasks)
    n_mut = sum(1 for t in tasks if TOOLS[t.tool].mutating)
    content_hash = hashlib.sha256(
        json.dumps([(t.tool, t.arguments) for t in tasks], sort_keys=True).encode()).hexdigest()[:16]
    return Plan(request_id=d.get("request_id") or uuid.uuid4().hex[:12],
                intent=d.get("intent") or "multi_task",
                requires_confirmation=bool(d.get("requires_confirmation", n_mut > 0 or sensitive)),
                tasks=tasks, created_from=d.get("source_message") or "", content_hash=content_hash)
