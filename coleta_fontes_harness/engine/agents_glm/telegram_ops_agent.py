# engine/agents_glm/telegram_ops_agent.py
"""
Telegram Ops - PUBLICACAO DESLIGADA por padrao.
TELEGRAM_PUBLISH_ENABLED = False
"""
import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("aura.agent.telegram_ops")

TELEGRAM_PUBLISH_ENABLED = False
DB_PATH = Path("engine/data/aura_engine.db")

REWRITE_PROMPT = """
Voce e o HERMES, analista chefe do AURA QUANT-X.
Dica bruta capturada: "{raw_tip}"
Analise interna do banco de dados: {aura_metrics}
Sua tarefa:
1. Reescreva essa dica no padrao AURA (tom frio, tatico, militar).
2. Adicione a metrica do AURA para dar peso.
3. NUNCA mencione o canal original.
4. Formate em Markdown do Telegram com emojis taticos.
"""


class TelegramOpsAgent:
    def __init__(self):
        # PLACEHOLDERS - substitua sob supervisao
        self.source_channels = [-1001234567890, -1009876543210]
        self.vip_channel = -1001111222333

    def _extract_match_info(self, text: str) -> Optional[Dict]:
        match = re.search(r"(.*?)\s*x\s*(.*?)\s*[-:]\s*(.*)", text, re.IGNORECASE)
        if match:
            return {
                "home": match.group(1).strip(),
                "away": match.group(2).strip(),
                "market": match.group(3).strip(),
            }
        return None

    def _cross_reference_aura(self, match_info: Dict) -> str:
        if not DB_PATH.exists():
            return "Sem dados no banco AURA no momento."
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "SELECT ap_diff, minute FROM live_features WHERE home LIKE ? LIMIT 1",
                (f"%{match_info['home']}%",),
            )
            row = c.fetchone()
            conn.close()
            if row:
                return f"Confirmacao AURA: AP diff {row[0]} no minuto {row[1]}."
            return "Jogo nao esta sendo rastreado ao vivo no AURA."
        except Exception as e:
            return f"Erro ao consultar DB: {e}"

    async def process_and_publish(self, raw_tip: str, llm_callable, bot_app):
        if not TELEGRAM_PUBLISH_ENABLED:
            logger.warning("TELEGRAM_PUBLISH_ENABLED=False. Publicacao bloqueada.")
            return "PUBLISH_BLOCKED"
        match_info = self._extract_match_info(raw_tip)
        if not match_info:
            return
        aura_metrics = self._cross_reference_aura(match_info)
        prompt = REWRITE_PROMPT.format(raw_tip=raw_tip, aura_metrics=aura_metrics)
        rewritten_tip = await llm_callable(prompt)
        try:
            await bot_app.bot.send_message(
                chat_id=self.vip_channel,
                text=rewritten_tip,
                parse_mode="Markdown",
            )
            logger.info("Dica publicada: %s x %s", match_info["home"], match_info["away"])
        except Exception as e:
            logger.error("Erro ao publicar: %s", e)


TELEGRAM_OPS = TelegramOpsAgent()
