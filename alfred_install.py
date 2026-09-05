# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "scripts" / "aura_chat_agents.py"
MARKER = "# ALFRED_MAX_BRIDGE_V1"

BRIDGE = '''\n    # ALFRED_MAX_BRIDGE_V1: ponte local multi-tarefa, sem polling\n    if low.startswith(("alfred", "aura alfred", "aura:")):\n        try:\n            from alfred_capabilities import parse_command, run_command\n            command = re.sub(r"(?i)^(?:alfred|aura alfred|aura)[:,]?\\s*", "", msg).strip()\n            planned = parse_command(command)\n            sensitive = any(item.get("kind") in {"organize_desktop", "type_text", "remember", "create_folder"} for item in planned)\n            explicit = any(token in low for token in ("executa", "faz agora", "pode fazer", "autorizo"))\n            execute = bool(explicit and planned) if sensitive else bool(planned)\n            result = run_command(command, execute=execute)\n            prefix = "ALFRED executado" if execute else "ALFRED plano (diz AUTORIZO para executar acções sensíveis)"\n            return prefix + "\\n" + json.dumps(result, ensure_ascii=False, indent=2)\n        except Exception as exc:\n            return "ALFRED indisponível: " + str(exc)[:300]\n'''


def install() -> int:
    if not TARGET.exists():
        print(f"ERRO: não encontrei {TARGET}")
        return 2
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("ALFRED bridge já instalada")
        return 0
    needle = "    low = msg.lower()\n    if not msg:\n        return None"
    if needle not in text:
        print("ERRO: ponto de integração não encontrado; nenhum ficheiro foi alterado")
        return 3
    backup = TARGET.with_suffix(TARGET.suffix + ".alfred-backup-" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(TARGET, backup)
    text = text.replace(needle, "    low = msg.lower()\n" + BRIDGE + "    if not msg:\n        return None", 1)
    TARGET.write_text(text, encoding="utf-8")
    print(f"ALFRED bridge instalada; backup: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(install())
