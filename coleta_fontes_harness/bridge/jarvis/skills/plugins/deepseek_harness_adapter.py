# bridge/jarvis/skills/plugins/deepseek_harness_adapter.py
"""
Adapter DeepSeek Harness para AURA
Integra o Harness no sistema de skills e no roteador multi-LLM.
"""
from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

HARNESS_PATH = Path(os.environ.get("AURA_DEEPSEEK_HARNESS_PATH", r"C:\aura\deepseek-harness"))
ENABLED = os.environ.get("AURA_DEEPSEEK_HARNESS_ENABLED", "0") == "1"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")


class Skill:
    """Skill de integração com DeepSeek Harness."""

    name = "deepseek_harness"
    description = "Executa tarefas via DeepSeek Harness (dsh) + modelos locais"

    def run(self, action: str = "status", args: Optional[Dict[str, Any]] = None) -> str:
        if not ENABLED:
            return "DeepSeek Harness desabilitado. Defina AURA_DEEPSEEK_HARNESS_ENABLED=1 no AURA_RUNTIME.env"

        args = args or {}

        if action == "status":
            exists = HARNESS_PATH.exists()
            has_key = bool(API_KEY and API_KEY.startswith("sk-"))
            return (
                f"Harness path: {HARNESS_PATH}\n"
                f"Existe: {exists}\n"
                f"Enabled: {ENABLED}\n"
                f"API Key configurada: {has_key}"
            )

        if action == "web":
            try:
                # Inicia em nova janela
                subprocess.Popen(
                    ["pnpm", "dsh", "web"],
                    cwd=str(HARNESS_PATH),
                    shell=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                return "DeepSeek Harness iniciando em http://127.0.0.1:3080"
            except Exception as e:
                return f"Erro ao iniciar Web UI: {e}"

        if action == "open":
            webbrowser.open("http://127.0.0.1:3080")
            return "Abrindo http://127.0.0.1:3080 no navegador"

        if action == "run":
            prompt = args.get("prompt", "")
            if not prompt:
                return "Informe o prompt: args={'prompt': 'sua tarefa'}"
            # Placeholder para integração futura via Python SDK
            return f"[DeepSeek Harness] Tarefa recebida: {prompt[:300]}..."

        return f"Ação desconhecida: {action}. Use: status | web | open | run"


# Instância global
SKILL = Skill()
