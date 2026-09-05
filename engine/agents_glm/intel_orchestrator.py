# engine/agents_glm/intel_orchestrator.py
"""Intel Orchestrator - publica so se TELEGRAM_PUBLISH_ENABLED=True."""
import logging
import re

logger = logging.getLogger("aura.agent.orchestrator")

try:
    from engine.agents_glm.general_intel_db import INTEL_DB
except Exception:
    INTEL_DB = None

try:
    from engine.agents_glm.telegram_ops_agent import TELEGRAM_PUBLISH_ENABLED
except Exception:
    TELEGRAM_PUBLISH_ENABLED = False

INTEL_PROMPT = """
Voce e o HERMES, analista chefe do AURA QUANT-X.
Dica bruta: "{raw_tip}"
Probabilidade implicita: {implied_prob}
Sua tarefa:
1. Reescreva a dica no padrao AURA (tom frio, tatico, militar).
2. Adicione um comentario sobre o valor da odd.
3. NUNCA mencione a fonte original.
4. Formate em Markdown do Telegram.
"""


class IntelOrchestrator:
    def __init__(self):
        self.regex_pattern = re.compile(
            r"(.*?)\s*(?:x|vs|X)\s*(.*?)\s*[-:]\s*(.*?)\s*[-:|@]\s*([\d\.]+)"
        )

    def _parse_tip(self, raw_text: str) -> dict:
        match = self.regex_pattern.search(raw_text)
        if match:
            return {
                "home": match.group(1).strip(),
                "away": match.group(2).strip(),
                "market": match.group(3).strip(),
                "odd": float(match.group(4).strip()),
            }
        return None

    async def process_and_publish(self, raw_tip: str, source: str, llm_callable, bot_app, vip_channel_id: int):
        if not TELEGRAM_PUBLISH_ENABLED:
            logger.warning("TELEGRAM_PUBLISH_ENABLED=False. Orchestrator nao publica.")
            return "PUBLISH_BLOCKED"
        if INTEL_DB is None:
            return "INTEL_DB indisponivel."
        tip_data = self._parse_tip(raw_tip)
        if not tip_data or tip_data["odd"] <= 1.0:
            return
        validation = "Validado pelo banco de dados interno."
        implied_prob = INTEL_DB.save_tip(
            source=source,
            raw=raw_tip,
            home=tip_data["home"],
            away=tip_data["away"],
            market=tip_data["market"],
            odd=tip_data["odd"],
            validation=validation,
        )
        prompt = INTEL_PROMPT.format(raw_tip=raw_tip, implied_prob=f"{implied_prob:.1f}%")
        rewritten_tip = await llm_callable(prompt)
        try:
            await bot_app.bot.send_message(
                chat_id=vip_channel_id,
                text=rewritten_tip,
                parse_mode="Markdown",
            )
            logger.info("Tip publicado: %s x %s", tip_data["home"], tip_data["away"])
        except Exception as e:
            logger.error("Erro ao publicar: %s", e)


INTEL_ORCHESTRATOR = IntelOrchestrator()
