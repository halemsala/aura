"""Wire codec: length-prefixed zlib payload.

Default: JSON (safe, fixed schema).
Optional: pickle only if AURA_GRID_ALLOW_PICKLE=true (UNSAFE — can RCE; LAN+trusted only).
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from typing import Any, Mapping

MAX_MSG = 32 * 1024 * 1024  # 32 MiB uncompressed cap after inflate


def _allow_pickle() -> bool:
    return os.environ.get("AURA_GRID_ALLOW_PICKLE", "").lower() in {"1", "true", "yes"}


def encode(obj: Mapping[str, Any] | dict) -> bytes:
    mode = "pickle" if _allow_pickle() else "json"
    if mode == "pickle":
        import pickle
        raw = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
        tag = b"P"
    else:
        raw = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        tag = b"J"
    compressed = zlib.compress(raw, level=6)
    # header: 4-byte length of (1-byte tag + compressed)
    body = tag + compressed
    if len(body) > MAX_MSG:
        raise ValueError("encoded message too large")
    return struct.pack(">I", len(body)) + body


def decode(blob: bytes) -> dict[str, Any]:
    if len(blob) < 1:
        raise ValueError("empty body")
    tag, compressed = blob[:1], blob[1:]
    raw = zlib.decompress(compressed)
    if len(raw) > MAX_MSG:
        raise ValueError("decompressed message too large")
    if tag == b"J":
        obj = json.loads(raw.decode("utf-8"))
    elif tag == b"P":
        if not _allow_pickle():
            raise ValueError("pickle payload rejected (AURA_GRID_ALLOW_PICKLE not set)")
        import pickle
        obj = pickle.loads(raw)  # trusted channel only
    else:
        raise ValueError(f"unknown codec tag {tag!r}")
    if not isinstance(obj, dict):
        raise TypeError("message must be a dict")
    return obj


def send_msg(sock, obj: Mapping[str, Any]) -> None:
    packet = encode(obj)
    sock.sendall(packet)


def _recvall(sock, n: int) -> bytes | None:
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


def recv_msg(sock) -> dict[str, Any] | None:
    hdr = _recvall(sock, 4)
    if not hdr:
        return None
    (n,) = struct.unpack(">I", hdr)
    if n > MAX_MSG:
        raise ValueError("declared size too large")
    body = _recvall(sock, n)
    if body is None:
        return None
    return decode(body)
