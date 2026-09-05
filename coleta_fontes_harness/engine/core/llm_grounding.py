from __future__ import annotations
import re
from typing import Dict

AURA_SYSTEM_PROMPT_V23_GROUNDED = """Voce e AURA V23. Analista quantitativo de escanteios.
FORMATO: "FATO: <fato> | EDGE: <valor> | DECISAO: <HOLD|NO_BET>"
REGRAS:
1. Use APENAS numeros em [CTX]. Nunca invente.
2. Se [CTX] sem dado: "FATO: Sem dado | EDGE: N/D | DECISAO: HOLD"
3. Max 12 palavras.
4. paper_trade=true. execution_allowed=false. Nunca ordem real.
"""


def validate_llm_output(reply: str, snapshot: Dict) -> str:
    numbers = re.findall(r"edge[:\s]+(\d+\.?\d*)", (reply or "").lower())
    if numbers:
        real_edge = snapshot.get("edge") or snapshot.get("calculated_edge")
        if real_edge is not None:
            try:
                if abs(float(numbers[0]) - float(real_edge)) > 0.05:
                    return "FATO: Dado inconsistente | EDGE: N/D | DECISAO: HOLD"
            except ValueError:
                pass
    return reply or "FATO: Sem resposta | EDGE: N/D | DECISAO: HOLD"


def deterministic_reply(intent: str, snapshot: Dict) -> str:
    edge = snapshot.get("edge") or snapshot.get("calculated_edge") or "N/D"
    decision = snapshot.get("decision") or "HOLD"
    corners = snapshot.get("corners") or [0, 0]
    minute = snapshot.get("minute") or "N/D"
    if isinstance(corners, (list, tuple)) and len(corners) >= 2:
        cstr = f"{corners[0]}-{corners[1]}"
    else:
        cstr = str(corners)
    if intent == "status":
        return f"FATO: Min {minute}, cantos {cstr} | EDGE: {edge} | DECISAO: {decision}"
    if intent == "edge":
        return f"FATO: Edge atual | EDGE: {edge} | DECISAO: {decision}"
    return "FATO: Comando nao reconhecido | EDGE: N/D | DECISAO: HOLD"
