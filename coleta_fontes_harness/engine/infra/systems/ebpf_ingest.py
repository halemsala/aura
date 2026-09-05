from __future__ import annotations
import mmap
import os
import struct
import threading
import time
from pathlib import Path
from typing import Dict, Optional

SHM_PATH = (
    str(Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "aura_ebpf_ring.dat")
    if os.name == "nt"
    else "/tmp/aura_ebpf_ring.dat"
)
SLOT_SIZE = 32  # ts_f64, corners_i32, line_f64, odds_f64 -> padded
N_SLOTS = 256

class EBPFRingBuffer:
    """Userspace mirror of eBPF ring buffer. Production: attach C eBPF to TC/XDP."""
    def __init__(self, path: str = SHM_PATH) -> None:
        self.path = path
        size = SLOT_SIZE * N_SLOTS + 8
        if not Path(path).exists():
            with open(path, "wb") as f:
                f.write(b"\x00" * size)
        self._fd = open(path, "r+b")
        self._buf = mmap.mmap(self._fd.fileno(), size)
        self._lock = threading.Lock()

    def write_tick(self, corners: int, line: float, odds: float) -> None:
        with self._lock:
            idx = struct.unpack_from("<Q", self._buf, 0)[0] % N_SLOTS
            off = 8 + int(idx) * SLOT_SIZE
            struct.pack_into("<dIdd", self._buf, off, time.time(), int(corners), float(line), float(odds))
            struct.pack_into("<Q", self._buf, 0, idx + 1)
            self._buf.flush()

    def read_latest(self) -> Optional[Dict[str, float]]:
        with self._lock:
            idx = struct.unpack_from("<Q", self._buf, 0)[0]
            if idx == 0:
                return None
            last = int((idx - 1) % N_SLOTS)
            off = 8 + last * SLOT_SIZE
            ts, corners, line, odds = struct.unpack_from("<dIdd", self._buf, off)
            return {"ts": ts, "corners": float(corners), "line": line, "odds": odds}

    def close(self) -> None:
        self._buf.close()
        self._fd.close()

# Stub note for real eBPF C program path
EBPF_C_STUB = "engine/infra/systems/ebpf_corner_filter.c"
