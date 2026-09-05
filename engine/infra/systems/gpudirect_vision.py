from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional

class GPUDirectFrameLoader:
    """Interface for NVMe->VRAM path. Falls back to normal open if GDS unavailable."""
    def __init__(self) -> None:
        self.gds = False
        try:
            import torch
            self.torch = torch
            # Real GDS requires nvidia-fs / cuFile; detect CUDA only
            self.cuda = torch.cuda.is_available()
        except Exception:
            self.torch = None
            self.cuda = False

    def load_frame(self, path: str) -> Dict[str, Any]:
        p = Path(path)
        if not p.exists():
            return {"ok": False, "error": "missing_frame", "gds": False}
        data = p.read_bytes()
        meta = {"ok": True, "bytes": len(data), "gds": self.gds, "cuda": self.cuda, "path": str(p)}
        if self.torch is not None and self.cuda:
            # Standard H2D copy (GDS would skip host bounce buffer)
            t = self.torch.frombuffer(bytearray(data[: min(len(data), 1024)]), dtype=self.torch.uint8)
            t = t.to("cuda", non_blocking=True)
            meta["device"] = str(t.device)
            meta["tensor_len"] = int(t.numel())
        else:
            meta["device"] = "cpu"
        return meta
