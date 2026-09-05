# bridge/jarvis/memory/semantic_memory.py
"""Semantic Memory via ChromaDB - SEMANTIC_MEMORY_ENABLED=False ate instalar chromadb."""
import logging
import uuid

logger = logging.getLogger("aura.memory.semantic")

SEMANTIC_MEMORY_ENABLED = False


class SemanticMemory:
    def __init__(self):
        self.client = None
        self.collection = None
        if not SEMANTIC_MEMORY_ENABLED:
            logger.info("SemanticMemory desabilitado (SEMANTIC_MEMORY_ENABLED=False).")
            return
        try:
            import chromadb
            self.client = chromadb.PersistentClient(path="engine/data/chroma_db")
            self.collection = self.client.get_or_create_collection(name="jarvis_memory")
        except Exception as e:
            logger.error("ChromaDB indisponivel: %s", e)

    def remember(self, text: str, metadata: dict):
        if not self.collection:
            return
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[str(uuid.uuid4())],
        )

    def recall(self, query: str, n_results: int = 1) -> str:
        if not self.collection:
            return "SemanticMemory desabilitado ou ChromaDB ausente."
        results = self.collection.query(query_texts=[query], n_results=n_results)
        if results.get("documents") and results["documents"][0]:
            return results["documents"][0][0]
        return "Nenhuma memoria encontrada."


SEMANTIC_MEMORY = SemanticMemory()
