"""AURA Grid v6.0 — cert pin, audit JSONL, result verification."""
from .worker import GridWorker, SystemMonitor, set_low_priority
from .master import GridMaster, MAX_RETRIES, TASKS_PER_CORE, VERIFICATION_RATE
from .ops import FIXED_OPS, run_fixed_op
from .codec import send_msg, recv_msg, encode, decode
from .pool_ops import process_batch_item
from .pinning import cert_sha256_pem_file, expected_pin
from .audit import AuditLogger
from .status_registry import StatusRegistry, format_status_table
from .manager import load_status

__version__ = "6.1.0"
__all__ = [
    "GridWorker", "GridMaster", "SystemMonitor", "set_low_priority",
    "FIXED_OPS", "run_fixed_op", "send_msg", "recv_msg", "encode", "decode",
    "process_batch_item", "MAX_RETRIES", "TASKS_PER_CORE", "VERIFICATION_RATE",
    "cert_sha256_pem_file", "expected_pin", "AuditLogger", "StatusRegistry", "format_status_table", "load_status",
]
