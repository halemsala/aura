"""Optional TLS for AURA Grid. Prefer real certs; self-signed for LAN lab only."""
from __future__ import annotations

import os
import ssl
from pathlib import Path


def client_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ca = os.environ.get("AURA_GRID_TLS_CA")
    if ca and Path(ca).is_file():
        ctx.load_verify_locations(ca)
        ctx.check_hostname = os.environ.get("AURA_GRID_TLS_CHECK_HOSTNAME", "true").lower() in {
            "1", "true", "yes"
        }
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        # lab mode — explicit opt-in
        if os.environ.get("AURA_GRID_TLS_INSECURE", "").lower() not in {"1", "true", "yes"}:
            raise RuntimeError(
                "TLS client requires AURA_GRID_TLS_CA or AURA_GRID_TLS_INSECURE=true (lab only)"
            )
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def server_context(certfile: str, keyfile: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    return ctx


def tls_enabled() -> bool:
    return os.environ.get("AURA_GRID_TLS", "").lower() in {"1", "true", "yes"}
