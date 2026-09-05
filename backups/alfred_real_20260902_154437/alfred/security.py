import secrets
from . import paths, util

def get_local_token() -> str:
    if paths.TOKEN_PATH.exists():
        tok = paths.TOKEN_PATH.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_hex(16)
    paths.TOKEN_PATH.write_text(tok + "\n", encoding="utf-8")
    try:
        os_chmod = getattr(__import__("os"), "chmod", None)
        if os_chmod:
            os_chmod(paths.TOKEN_PATH, 0o600)
    except Exception:
        pass
    return tok
