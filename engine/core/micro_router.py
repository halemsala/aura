"""
AURA QUANT-X :: Ultra-Performance Micro-Router (V23)
Lazy-loading de agentes + limite de concorrencia + timeout.
Nao substitui integralmente server.py; e o dispatch opcional.
"""
from __future__ import annotations
import asyncio
import importlib
import logging
from functools import lru_cache
from typing import Any, Dict, Protocol

logger = logging.getLogger("Aura.MicroRouter")


class IAgentExecutable(Protocol):
    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...


@lru_cache(maxsize=64)
def _lazy_import_agent(agent_module_path: str):
    try:
        module = importlib.import_module(agent_module_path)
        agent_class = getattr(module, "Agent", getattr(module, "Handler", None))
        if agent_class is None:
            raise AttributeError(f"Modulo {agent_module_path} nao exporta Agent ou Handler")
        return agent_class
    except Exception as e:
        logger.critical("FALHA LAZY IMPORT: %s | %s", agent_module_path, e)
        raise


class AuraMicroRouter:
    def __init__(self, max_concurrent_agents: int = 100):
        self._concurrency_limiter = asyncio.Semaphore(max_concurrent_agents)

    async def dispatch(self, agent_path: str, payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
        async with self._concurrency_limiter:
            try:
                agent_class = _lazy_import_agent(agent_path)
                agent_instance = agent_class()
                return await asyncio.wait_for(agent_instance.execute(payload), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error("Timeout no agente %s apos %ss", agent_path, timeout)
                return {
                    "status": "error",
                    "code": "AGENT_TIMEOUT",
                    "agent": agent_path,
                    "paper_trade": True,
                    "execution_allowed": False,
                }
            except Exception as e:
                logger.error("Falha no agente %s: %s", agent_path, e, exc_info=False)
                return {
                    "status": "error",
                    "code": "AGENT_EXCEPTION",
                    "message": str(e),
                    "paper_trade": True,
                    "execution_allowed": False,
                }


router_instance = AuraMicroRouter()
