# Item 66 — checksum de pesos
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Optional


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_weights(weights_path: str, report_path: str = "train_report.json") -> bool:
    p = Path(weights_path)
    if not p.exists():
        return False
    digest = sha256_file(weights_path)
    rp = Path(report_path)
    if not rp.exists():
        # grava digest atual
        data = {"weights_sha256": digest, "weights": weights_path}
        rp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
        expected = data.get("weights_sha256")
        if not expected:
            data["weights_sha256"] = digest
            rp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        return expected == digest
    except Exception:
        return False
