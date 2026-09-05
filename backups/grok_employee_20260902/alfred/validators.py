import os, re, unicodedata
from pathlib import Path
from urllib.parse import urlparse
from . import paths
from .config import get_config


class ValidationError(ValueError):
    """Violação de contrato de segurança/validação."""


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


# ---------- URLs ----------
BLOCKED_SCHEMES = {"file", "javascript", "data", "vbscript", "about", "chrome", "res", "blob"}
MAX_URL_LEN = 2048

def validate_url(raw) -> str:
    u = str(raw or "").strip()
    if not u or len(u) > MAX_URL_LEN:
        raise ValidationError("URL vazio ou excede 2048 caracteres")
    if any(c in u for c in "\r\n\x00\t"):
        raise ValidationError("URL contém caracteres de controlo")
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        raise ValidationError(f"esquema não permitido: '{p.scheme or '(vazio)'}' (só http/https)")
    if not p.netloc:
        raise ValidationError("URL sem host")
    if "@" in p.netloc:
        raise ValidationError("URL com credenciais embutidas bloqueado")
    return u


# ---------- Ficheiros ----------
def home_dir() -> Path:
    override = os.environ.get("ALFRED_TEST_HOME")
    return Path(override) if override else Path.home()

def user_roots() -> list:
    roots = [home_dir() / n for n in get_config().get("allowed_roots", ["Desktop", "Documents", "Downloads"])]
    roots.append(paths.DATA_ROOT)
    roots.append(paths.PROJECT_ROOT)
    return [Path(r).resolve() for r in roots]

SECRET_FILE_HINTS = (".pem", ".key", ".pfx", ".p12", ".kdbx", ".env", "wallet.dat", ".ppk")
SECRET_NAME_RE = re.compile(r"(?i)(id_rsa|id_ed25519|id_ecdsa|credentials|password|secret|private[_-]?key)")
SYSTEM_DIR_HINTS = {"windows", "program files", "program files (x86)", "programdata", "system volume information"}

def path_is_secret(p: Path) -> bool:
    n = p.name.casefold()
    return any(n.endswith(h) for h in SECRET_FILE_HINTS) or bool(SECRET_NAME_RE.search(n))

def resolve_allowed(raw, base_root=None) -> Path:
    raw = str(raw or "").strip()
    if not raw:
        raise ValidationError("caminho vazio")
    if raw.startswith("\\\\"):
        raise ValidationError("caminhos UNC não permitidos")
    if ".." in Path(raw).parts or "/.." in raw or "\\..\\" in raw:
        raise ValidationError("traversal ('..') bloqueado")
    p = Path(raw).expanduser()
    if p.is_absolute():
        cand = Path(os.path.realpath(p))
    else:
        parts = [x for x in p.parts if x not in (".", "")]
        first = parts[0].casefold() if parts else ""
        roots = {r.name.casefold(): r for r in user_roots()}
        if first in roots:
            cand = Path(os.path.realpath(roots[first].joinpath(*parts[1:])))
        elif first in ("data", "alfred", "dados", "data\\alfred"):
            cand = Path(os.path.realpath(paths.DATA_ROOT.joinpath(*parts[1:])))
        else:
            base = Path(base_root) if base_root else home_dir() / "Desktop"
            cand = Path(os.path.realpath(base.joinpath(*parts)))
    cl = str(cand).casefold()
    if cl.startswith("\\\\"):
        raise ValidationError("caminhos UNC não permitidos")
    ok = False
    for r in user_roots():
        rl = str(r).casefold()
        if cl == rl or cl.startswith(rl + os.sep):
            ok = True
            break
    if not ok:
        raise ValidationError(f"caminho fora da allowlist: {cand}")
    if not cl.startswith(str(paths.DATA_ROOT).casefold()):
        for part in cand.parts:
            if part.casefold() in SYSTEM_DIR_HINTS:
                raise ValidationError("directório de sistema bloqueado")
    if path_is_secret(cand):
        raise ValidationError("ficheiro protegido (chaves/credenciais) bloqueado")
    return cand


# ---------- Segredos em texto ----------
SECRET_RES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"(?i)\b(password|passwd|palavra[ _-]?passe|api[ _-]?key|token|secret)\b\s*[:=]\s*\S+"),
]

def detect_secrets(text: str) -> list:
    return [rx.pattern for rx in SECRET_RES if rx.search(text or "")]
