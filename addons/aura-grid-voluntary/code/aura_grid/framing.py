"""Backward-compatible framing API — delegates to codec (JSON+zlib default)."""
from __future__ import annotations

from .codec import encode, decode, send_msg, recv_msg

__all__ = ["encode", "decode", "send_msg", "recv_msg"]
