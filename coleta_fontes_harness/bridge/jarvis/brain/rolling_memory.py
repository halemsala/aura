# bridge/jarvis/brain/rolling_memory.py
"""
Rolling Memory Manager v1.0
Mantem o contexto compacto (3 turnos) e resume dados antigos.
"""
import logging
from collections import deque

logger = logging.getLogger("aura.memory.rolling")


class RollingMemory:
    def __init__(self, max_recent: int = 3):
        self.recent_history = deque(maxlen=max_recent)
        self.summarized_context = "Nenhuma conversa anterior relevante."

    def add_interaction(self, user_msg: str, ai_msg: str):
        self.recent_history.append({"user": user_msg, "ai": ai_msg})

    def get_prompt_context(self) -> str:
        context = f"### CONTEXTO RESUMIDO:\n{self.summarized_context}\n\n### CONVERSA RECENTE:\n"
        for turn in self.recent_history:
            context += f"Operador: {turn['user']}\nHERMES: {turn['ai']}\n"
        return context

    async def compact_memory(self, llm_summarizer):
        if len(self.recent_history) < self.recent_history.maxlen:
            return
        oldest = self.recent_history[0]
        prompt = f"Resuma em UMA frase: Operador disse '{oldest['user']}', voce respondeu '{oldest['ai']}'."
        summary = await llm_summarizer(prompt)
        self.summarized_context += f"\n- {summary}"
        self.recent_history.popleft()


ROLLING_MEMORY = RollingMemory()
