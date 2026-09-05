# bridge/cognitive/intent_trie.py — Auditoria Radical 2.2
from __future__ import annotations
from typing import Any


class IntentTrie:
    __slots__ = ("_root",)

    def __init__(self) -> None:
        self._root: dict = {}

    def register(self, tokens: list[str], handler: str, priority: int = 0) -> None:
        node = self._root
        for tok in tokens:
            node = node.setdefault(tok.lower(), {})
        node["__intent__"] = (handler, priority)

    def resolve(self, text: str) -> dict[str, Any]:
        words = (text or "").lower().split()
        best = None
        best_pri = -1
        for i in range(len(words)):
            node = self._root
            for j in range(i, min(i + 6, len(words))):
                node = node.get(words[j])
                if node is None:
                    break
                if "__intent__" in node:
                    intent, pri = node["__intent__"]
                    if pri > best_pri:
                        best_pri = pri
                        best = intent
        if best:
            return {"intent": best, "needs_glm": False, "confidence": 1.0}
        return {"intent": "complex", "needs_glm": True, "confidence": 0.0}


def build_default_trie() -> IntentTrie:
    trie = IntentTrie()
    trie.register(["status", "sistema"], "system_command", 10)
    trie.register(["health"], "system_command", 10)
    trie.register(["reiniciar"], "restricted_request", 10)
    trie.register(["analisar", "corner"], "tactical_analysis", 5)
    trie.register(["analisar", "escanteio"], "tactical_analysis", 5)
    trie.register(["hold"], "advisory_hold", 8)
    return trie
