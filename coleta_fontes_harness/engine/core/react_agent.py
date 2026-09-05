from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger("aura.react_agent")


@dataclass
class AttemptResult:
    ok: bool
    value: Any = None
    error: Optional[str] = None
    reasoning: str = ""
    attempt_index: int = 0
    elapsed_ms: float = 0.0


@dataclass
class ReActTrace:
    tool_name: str
    attempts: List[AttemptResult] = field(default_factory=list)
    healed: bool = False
    final_ok: bool = False
    total_elapsed_ms: float = 0.0


class ReActAgentMixin:
    """Resiliencia Reason-Act-Observe. Apenas leitura/analise/paper-trade."""

    def _react_max_attempts(self) -> int:
        return int(getattr(self, "REACT_MAX_ATTEMPTS", 3))

    def _react_backoff_base_s(self) -> float:
        return float(getattr(self, "REACT_BACKOFF_BASE_S", 0.5))

    def _react_deadline_s(self) -> float:
        return float(getattr(self, "REACT_DEADLINE_S", 8.0))

    async def react_call(
        self,
        tool_name: str,
        act_fn: Callable[[], Awaitable[Any]],
        *,
        heal_fn: Optional[Callable[[Exception, int], Awaitable[None]]] = None,
        alternate_fn: Optional[Callable[[], Awaitable[Any]]] = None,
        validate_fn: Optional[Callable[[Any], bool]] = None,
    ) -> ReActTrace:
        trace = ReActTrace(tool_name=tool_name)
        t_start = time.monotonic()
        max_attempts = self._react_max_attempts()
        # PATCH V23-P1 (item 4.3 da auditoria): a escolha de função na
        # próxima tentativa agora depende do resultado real do heal, não
        # da paridade do contador. Original: `attempt % 2 == 0` alternava
        # para alternate_fn em tentativas pares independentemente de
        # heal_fn ter corrigido algo — então uma cura bem-sucedida na
        # tentativa 1 podia ser descartada trocando de função na tentativa
        # 2 mesmo assim, e uma cura malsucedida podia repetir act_fn sem
        # necessidade. Regra nova: se o heal reportou sucesso, tenta de
        # novo com a função primária; só cai para alternate_fn quando não
        # houve heal_fn, ou quando o heal_fn mais recente falhou/não foi
        # chamado (ainda não há healed=True para justificar repetir a
        # primária).
        last_heal_succeeded = False
        budget = self._react_deadline_s()
        for attempt in range(1, max_attempts + 1):
            if time.monotonic() - t_start >= budget:
                break
            use_alternate = alternate_fn is not None and attempt > 1 and not last_heal_succeeded
            fn = alternate_fn if use_alternate else act_fn
            reasoning = f"Tentativa {attempt}/{max_attempts} via {'alternativo' if use_alternate else 'primario'}"
            t0 = time.monotonic()
            try:
                value = await fn()
                if validate_fn is not None and not validate_fn(value):
                    raise ValueError("validate_fn rejeitou resultado")
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                trace.attempts.append(AttemptResult(True, value, None, reasoning, attempt, elapsed_ms))
                trace.final_ok = True
                trace.total_elapsed_ms = (time.monotonic() - t_start) * 1000.0
                return trace
            except Exception as exc:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                trace.attempts.append(AttemptResult(False, None, f"{type(exc).__name__}: {exc}", reasoning, attempt, elapsed_ms))
                last_heal_succeeded = False
                if attempt < max_attempts:
                    if heal_fn is not None:
                        try:
                            await heal_fn(exc, attempt)
                            trace.healed = True
                            last_heal_succeeded = True
                        except Exception as heal_exc:
                            logger.error("[ReAct:%s] heal fail: %s", tool_name, heal_exc)
                    await asyncio.sleep(self._react_backoff_base_s() * (2 ** (attempt - 1)))
        trace.total_elapsed_ms = (time.monotonic() - t_start) * 1000.0
        return trace
