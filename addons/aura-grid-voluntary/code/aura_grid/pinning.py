"""TLS certificate pinning helpers."""
from __future__ import annotations

import hashlib
import os
import ssl
from pathlib import Path


def cert_sha256_der(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def cert_sha256_pem_file(path: str | Path) -> str:
    pem = Path(path).read_text(encoding="utf-8")
    der = ssl.PEM_cert_to_DER_cert(pem)
    return cert_sha256_der(der)


def expected_pin() -> str | None:
    pin = os.environ.get("AURA_GRID_CERT_PIN", "").strip().lower()
    return pin or None


def verify_peer_pin(ssl_sock) -> tuple[bool, str]:
    """Return (ok, actual_hash). If no pin configured, returns (True, actual_or_empty)."""
    try:
        der = ssl_sock.getpeercert(binary_form=True)
    except Exception as e:
        return False, f"no_peer_cert:{e}"
    if not der:
        return False, "empty_peer_cert"
    actual = cert_sha256_der(der)
    pin = expected_pin()
    if not pin:
        return True, actual  # pinning not enforced
    return actual == pin, actual
