# engine/agents_glm/system_medic_agent.py
"""
System Medic Agent v1.0
Diagnostica falhas em tempo de execucao (portas, hardware, SQLite).
Nao reinicia servicos sozinho — apenas emite laudo.
"""
from __future__ import annotations
import logging
import socket
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict

logger = logging.getLogger("aura.agent.medic")

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False
    psutil = None


class SystemMedicAgent:
    def __init__(self):
        self.ports = {
            "Bridge": 8080,
            "Engine": 8765,
            "Voice": 8099,
            "Ollama": 11434,
        }

    def _check_port(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                return s.connect_ex(("127.0.0.1", port)) == 0
        except Exception:
            return False

    def _check_db_integrity(self, db_path: Path) -> str:
        if not db_path.exists():
            return "DB Ausente"
        try:
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("PRAGMA integrity_check;")
            result = c.fetchone()[0]
            conn.close()
            return result
        except Exception as e:
            return f"Corrompido: {e}"

    def full_diagnosis(self) -> Dict:
        logger.info("Iniciando diagnostico completo do sistema...")
        report: Dict = {
            "timestamp": datetime.now().isoformat(),
            "ports": {},
            "hardware": {},
            "database": {},
            "errors_found": [],
        }

        for name, port in self.ports.items():
            is_alive = self._check_port(port)
            report["ports"][name] = "ONLINE" if is_alive else "OFFLINE"
            if not is_alive:
                report["errors_found"].append(
                    f"Servico {name} (porta {port}) esta OFFLINE."
                )

        if PSUTIL_OK:
            cpu_per = psutil.cpu_percent(interval=0.5)
            ram_per = psutil.virtual_memory().percent
            report["hardware"]["cpu"] = f"{cpu_per}%"
            report["hardware"]["ram"] = f"{ram_per}%"
            if cpu_per > 90:
                report["errors_found"].append(
                    "Uso de CPU Critico (>90%). Risco de lag no Motor AURA."
                )
            if ram_per > 90:
                report["errors_found"].append("Uso de RAM Critico (>90%).")
        else:
            report["hardware"]["cpu"] = "psutil_ausente"
            report["hardware"]["ram"] = "psutil_ausente"

        for db_name in ["aura_engine.db", "tips_intel.db", "jarvis_memory.db"]:
            db_path = Path("engine/data") / db_name
            status = self._check_db_integrity(db_path)
            report["database"][db_name] = status
            if status != "ok" and status != "DB Ausente":
                report["errors_found"].append(
                    f"Banco {db_name} com problema: {status}."
                )

        return report


SYSTEM_MEDIC = SystemMedicAgent()
