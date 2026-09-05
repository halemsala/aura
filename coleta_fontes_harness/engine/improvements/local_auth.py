# local_auth.py
# Autenticação local por token de instalação (modo hardened)
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from typing import Optional, Tuple

# Em produção o token deve vir de arquivo de instalação ou variável de ambiente
# nunca hardcoded no código distribuído.
ENV_TOKEN = "CORNERAI_INSTALL_TOKEN"
ENV_MODE = "CORNERAI_MODE"  # "dev" | "hardened"


def current_mode() -> str:
    return os.getenv(ENV_MODE, "dev").lower()


def is_hardened() -> bool:
    return current_mode() == "hardened"


def get_expected_token() -> Optional[str]:
    return os.getenv(ENV_TOKEN) or None


def generate_install_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def validate_request_token(provided: Optional[str]) -> Tuple[bool, str]:
    """
    Retorna (ok, reason).
    Em modo dev: sempre ok (com aviso).
    Em modo hardened: token obrigatório e comparado em tempo constante.
    """
    if not is_hardened():
        return True, "dev_mode_open"
    expected = get_expected_token()
    if not expected:
        return False, "HARDENED_BUT_NO_TOKEN_CONFIGURED"
    if not provided:
        return False, "TOKEN_MISSING"
    if not constant_time_compare(provided.strip(), expected.strip()):
        return False, "TOKEN_MISMATCH"
    return True, "OK"
