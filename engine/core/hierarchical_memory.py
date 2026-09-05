"""
AURA QUANT-X :: Hierarchical Semantic Memory (V23)
Curto prazo + longo prazo vetorial (NumPy). Fallback sem embedding real.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import hashlib

try:
    import numpy as np
except Exception:
    np = None  # type: ignore


@dataclass
class MemoryConfig:
    short_term_limit: int = 5
    long_term_max_size: int = 500
    embedding_dim: int = 384


class HierarchicalMemory:
    def __init__(self, config: Optional[MemoryConfig] = None, embedding_fn: Optional[Callable[[str], list]] = None):
        self.cfg = config or MemoryConfig()
        self._embedding_fn = embedding_fn
        self.short_term: List[Dict[str, str]] = []
        if np is not None:
            self._lt_vectors = np.empty((0, self.cfg.embedding_dim), dtype=np.float32)
        else:
            self._lt_vectors = None
        self._lt_texts: List[str] = []

    def _get_embedding(self, text: str):
        if np is None:
            return None
        if self._embedding_fn:
            return np.array(self._embedding_fn(text), dtype=np.float32)
        # fallback deterministico (nao aleatorio) para nao quebrar boot
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vals = [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(self.cfg.embedding_dim)]
        return np.array(vals, dtype=np.float32)

    def add_interaction(self, user_input: str, ai_response: str) -> None:
        self.short_term.append({"u": user_input, "a": ai_response})
        if len(self.short_term) > self.cfg.short_term_limit:
            popped = self.short_term.pop(0)
            self._push_to_long_term(popped["a"])

    def _push_to_long_term(self, text: str) -> None:
        if np is None or self._lt_vectors is None:
            self._lt_texts.append(text)
            if len(self._lt_texts) > self.cfg.long_term_max_size:
                self._lt_texts.pop(0)
            return
        if len(self._lt_texts) >= self.cfg.long_term_max_size:
            self._lt_vectors = self._lt_vectors[1:]
            self._lt_texts.pop(0)
        vec = self._get_embedding(text).reshape(1, -1)
        self._lt_vectors = np.vstack([self._lt_vectors, vec])
        self._lt_texts.append(text)

    def get_context_for_llm(self, current_query: str, top_k: int = 2) -> str:
        short_str = "\n".join([f"U: {t['u']}\nA: {t['a']}" for t in self.short_term])
        if np is None or self._lt_vectors is None or self._lt_vectors.shape[0] == 0:
            return f"CONVERSA RECENTE:\n{short_str}"
        q_vec = self._get_embedding(current_query)
        denom = np.linalg.norm(self._lt_vectors, axis=1) * (np.linalg.norm(q_vec) + 1e-8)
        similarities = np.dot(self._lt_vectors, q_vec) / (denom + 1e-8)
        k = min(top_k, len(self._lt_texts))
        top_indices = np.argpartition(similarities, -k)[-k:]
        retrieved = "\n".join(
            [self._lt_texts[i] for i in top_indices if similarities[i] > 0.3]
        )
        return f"CONTEXTO RELEVANTE PASSADO (RAG):\n{retrieved}\n\nCONVERSA ATUAL:\n{short_str}"


hierarchical_memory = HierarchicalMemory()
