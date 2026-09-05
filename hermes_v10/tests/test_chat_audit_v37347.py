# Offline regressions for V37.3.47 chat audit (no live services).
import re

ACTION_RE = re.compile(
    r"^\s*(?:autori[sz][oa]\s+|pode\s+|podes\s+)?"
    r"(corrige?|conserta?|arruma?|repara?|fix|diagn[oó]stic\w*|diag|"
    r"status|estado|reinicia?|restart|religa?|abre?|abra?|gpu|placa)"
    r"(?:\s+(?:engine|bridge|matriz|hermes|voz|voice|all|tudo|desktop|o\s+desktop|a\s+matriz|[0-9]{2,3}%?))?"
    r"\s*$",
    re.IGNORECASE,
)
FIX_CODE_RE = re.compile(r"^\s*(?:autorizo\s+|autoriso\s+)?fix\s+(e-[a-z]+-\d+)\s*$", re.IGNORECASE)
AUTH_RE = re.compile(r"\b(autorizo|autorizado|eu\s+autorizo|com\s+autoriza[cç][aã]o)\b", re.IGNORECASE)


def test_autorizo_corrige_is_pure_command():
    assert ACTION_RE.match("AUTORIZO corrige")
    assert ACTION_RE.match("autorizo corrige")
    assert ACTION_RE.match("autoriso corrige")  # typo old spelling still accepted


def test_old_autoris_only_pattern_would_fail_but_new_passes():
    old = re.compile(r"^\s*(?:autoris[oa]\s+)?corrige", re.IGNORECASE)
    assert not old.match("AUTORIZO corrige")
    assert ACTION_RE.match("AUTORIZO corrige")


def test_fix_code_optional_auth():
    assert FIX_CODE_RE.match("fix e-gpu-01").group(1).upper() == "E-GPU-01"
    assert FIX_CODE_RE.match("AUTORIZO fix e-net-004").group(1).upper() == "E-NET-004"


def test_auth_word_detects_z_and_s():
    assert AUTH_RE.search("AUTORIZO corrige")
    assert AUTH_RE.search("eu autorizo")
