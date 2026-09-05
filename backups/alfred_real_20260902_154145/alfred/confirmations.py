import re

AUTH_RE = re.compile(
    r"^\s*(?:ok[\s,]+)?(?:alfred[\s,]+)?(autorizo|autorizado|executa|execute|executar|faz agora|podes executar|run)\b",
    re.I)
CANCEL_RE = re.compile(r"^\s*(?:alfred[\s,]+)?(cancela|cancelar|para\!?|parar|stop|aborta|abortar)\b", re.I)

def is_authorization(text: str) -> bool:
    return bool(AUTH_RE.match((text or "").strip()))

def is_cancel(text: str) -> bool:
    return bool(CANCEL_RE.match((text or "").strip()))
