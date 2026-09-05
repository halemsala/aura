"""core/voice/latency_allocator.py — M/D/1-preemptive voice latency budget."""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger("aura.voice.latency")

TICK_S: float = 0.008
RESIDUAL_ABORT_MS: float = 95.0
EMA_ALPHA: float = 0.18
DEFAULT_BUDGET_MS: float = 450.0
SERVICE_MS_PER_TOKEN: float = 12.0


class CommandKind(str, enum.Enum):
    SPEAK = "SPEAK"
    RISK_CMD = "RISK_CMD"
    CANCEL = "CANCEL"
    FLUSH = "FLUSH"


class ResidualExhausted(Exception):
    def __init__(self, residual_ms: float, command_id: str) -> None:
        self.residual_ms = residual_ms
        self.command_id = command_id
        super().__init__(
            f"residual_exhausted residual_ms={residual_ms:.1f} cmd={command_id}"
        )


@dataclass(slots=True)
class LatencyBudget:
    total_ms: float
    started_at: float
    reserved_tts_ms: float = 120.0
    reserved_stt_ms: float = 80.0

    def elapsed_ms(self, now: Optional[float] = None) -> float:
        t = time.monotonic() if now is None else now
        return max(0.0, (t - self.started_at) * 1000.0)

    def residual_ms(self, now: Optional[float] = None) -> float:
        return self.total_ms - self.elapsed_ms(now)

    def residual_after_reservations_ms(self, now: Optional[float] = None) -> float:
        return self.residual_ms(now) - self.reserved_tts_ms - self.reserved_stt_ms


@dataclass(order=True, slots=True)
class VoiceCommand:
    priority: int
    seq: int
    kind: CommandKind = field(compare=False)
    command_id: str = field(compare=False)
    text: str = field(compare=False, default="")
    tokens_est: int = field(compare=False, default=0)
    budget: LatencyBudget = field(
        compare=False,
        default_factory=lambda: LatencyBudget(DEFAULT_BUDGET_MS, time.monotonic()),
    )
    enqueued_at: float = field(compare=False, default_factory=time.monotonic)
    preempt: bool = field(compare=False, default=False)


@dataclass(slots=True)
class AllocatorStats:
    served: int = 0
    preempted: int = 0
    aborted: int = 0
    tokens_ema: float = 0.0
    last_service_ms: float = 0.0
    queue_depth: int = 0


class LatencyAllocator:
    def __init__(
        self,
        default_budget_ms: float = DEFAULT_BUDGET_MS,
        tick_s: float = TICK_S,
    ) -> None:
        self._default_budget_ms = default_budget_ms
        self._tick_s = tick_s
        self._queue: asyncio.PriorityQueue[VoiceCommand] = asyncio.PriorityQueue()
        self._seq = 0
        self._stats = AllocatorStats()
        self._running: Optional[asyncio.Task[None]] = None
        self._current_task: Optional[asyncio.Task[Any]] = None
        self._current_cmd: Optional[VoiceCommand] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._token_samples: Deque[float] = deque(maxlen=64)

    @property
    def stats(self) -> AllocatorStats:
        self._stats.queue_depth = self._queue.qsize()
        return self._stats

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _priority_for(self, kind: CommandKind) -> int:
        if kind is CommandKind.RISK_CMD:
            return 0
        if kind is CommandKind.CANCEL:
            return 1
        if kind is CommandKind.FLUSH:
            return 2
        return 10

    async def start(self) -> None:
        if self._running and not self._running.done():
            return
        self._stop.clear()
        self._running = asyncio.create_task(self._tick_loop(), name="voice-latency-tick")

    async def stop(self) -> None:
        self._stop.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            try:
                await self._current_task
            except (asyncio.CancelledError, ResidualExhausted):
                pass
        if self._running:
            self._running.cancel()
            try:
                await self._running
            except asyncio.CancelledError:
                pass
            self._running = None

    async def submit(
        self,
        kind: CommandKind,
        command_id: str,
        text: str = "",
        tokens_est: int = 0,
        budget_ms: Optional[float] = None,
    ) -> None:
        if tokens_est <= 0 and text:
            tokens_est = max(1, len(text.split()))
        budget = LatencyBudget(
            total_ms=float(budget_ms if budget_ms is not None else self._default_budget_ms),
            started_at=time.monotonic(),
        )
        cmd = VoiceCommand(
            priority=self._priority_for(kind),
            seq=self._next_seq(),
            kind=kind,
            command_id=command_id,
            text=text,
            tokens_est=tokens_est,
            budget=budget,
            preempt=(kind is CommandKind.RISK_CMD),
        )
        if cmd.preempt and self._current_cmd is not None:
            if self._current_cmd.kind is not CommandKind.RISK_CMD:
                await self._preempt_current(cmd)
        await self._queue.put(cmd)
        self._stats.queue_depth = self._queue.qsize()

    async def _preempt_current(self, incoming: VoiceCommand) -> None:
        task = self._current_task
        if task is None or task.done():
            return
        self._stats.preempted += 1
        logger.info(
            "voice_preempt",
            extra={
                "event": "voice_preempt",
                "incoming": incoming.command_id,
                "victim": self._current_cmd.command_id if self._current_cmd else None,
                "kind": incoming.kind.value,
            },
        )
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, ResidualExhausted):
            pass
        self._current_task = None
        self._current_cmd = None

    async def _tick_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "voice_tick_error",
                    extra={"event": "voice_tick_error", "error": str(exc)},
                )
            await asyncio.sleep(self._tick_s)

    async def _tick_once(self) -> None:
        if self._current_task is not None and not self._current_task.done():
            cmd = self._current_cmd
            if cmd is not None:
                residual = cmd.budget.residual_ms()
                if residual < RESIDUAL_ABORT_MS:
                    self._stats.aborted += 1
                    logger.warning(
                        "voice_residual_abort",
                        extra={
                            "event": "voice_residual_abort",
                            "command_id": cmd.command_id,
                            "residual_ms": residual,
                            "threshold_ms": RESIDUAL_ABORT_MS,
                        },
                    )
                    self._current_task.cancel()
                    try:
                        await self._current_task
                    except (asyncio.CancelledError, ResidualExhausted):
                        pass
                    self._current_task = None
                    self._current_cmd = None
            return

        if self._queue.empty():
            return

        cmd = await self._queue.get()
        residual = cmd.budget.residual_ms()
        if residual < RESIDUAL_ABORT_MS:
            self._stats.aborted += 1
            logger.warning(
                "voice_residual_abort",
                extra={
                    "event": "voice_residual_abort",
                    "command_id": cmd.command_id,
                    "residual_ms": residual,
                    "threshold_ms": RESIDUAL_ABORT_MS,
                    "phase": "dequeue",
                },
            )
            self._queue.task_done()
            return

        if cmd.kind is CommandKind.CANCEL:
            await self._preempt_current(cmd)
            self._queue.task_done()
            return

        if cmd.kind is CommandKind.FLUSH:
            await self._flush_queue()
            self._queue.task_done()
            return

        self._current_cmd = cmd
        self._current_task = asyncio.create_task(
            self._serve(cmd), name=f"voice-serve-{cmd.command_id}"
        )
        try:
            await self._current_task
        except ResidualExhausted as exc:
            self._stats.aborted += 1
            logger.warning(
                "voice_residual_abort",
                extra={
                    "event": "voice_residual_abort",
                    "command_id": exc.command_id,
                    "residual_ms": exc.residual_ms,
                    "phase": "serve",
                },
            )
        except asyncio.CancelledError:
            pass
        finally:
            self._current_task = None
            self._current_cmd = None
            self._queue.task_done()

    async def _flush_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

    def _update_token_ema(self, tokens: int) -> float:
        prev = self._stats.tokens_ema
        if prev <= 0.0:
            ema = float(tokens)
        else:
            ema = EMA_ALPHA * float(tokens) + (1.0 - EMA_ALPHA) * prev
        self._stats.tokens_ema = ema
        self._token_samples.append(float(tokens))
        return ema

    async def _serve(self, cmd: VoiceCommand) -> None:
        tokens = max(1, cmd.tokens_est)
        self._update_token_ema(tokens)
        service_ms = tokens * SERVICE_MS_PER_TOKEN
        residual = cmd.budget.residual_after_reservations_ms()
        if residual < RESIDUAL_ABORT_MS:
            raise ResidualExhausted(residual, cmd.command_id)
        planned_ms = min(service_ms, max(0.0, residual - RESIDUAL_ABORT_MS))
        t0 = time.monotonic()
        remaining_s = planned_ms / 1000.0
        while remaining_s > 0.0:
            if cmd.budget.residual_ms() < RESIDUAL_ABORT_MS:
                raise ResidualExhausted(cmd.budget.residual_ms(), cmd.command_id)
            step = min(self._tick_s, remaining_s)
            await asyncio.sleep(step)
            remaining_s -= step
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        self._stats.last_service_ms = elapsed_ms
        self._stats.served += 1
        logger.info(
            "voice_served",
            extra={
                "event": "voice_served",
                "command_id": cmd.command_id,
                "kind": cmd.kind.value,
                "tokens": tokens,
                "tokens_ema": self._stats.tokens_ema,
                "service_ms": elapsed_ms,
                "residual_ms": cmd.budget.residual_ms(),
            },
        )

    def snapshot(self) -> Dict[str, Any]:
        s = self.stats
        return {
            "served": s.served,
            "preempted": s.preempted,
            "aborted": s.aborted,
            "tokens_ema": round(s.tokens_ema, 3),
            "last_service_ms": round(s.last_service_ms, 2),
            "queue_depth": s.queue_depth,
            "tick_ms": self._tick_s * 1000.0,
            "residual_abort_ms": RESIDUAL_ABORT_MS,
            "ema_alpha": EMA_ALPHA,
        }


_allocator: Optional[LatencyAllocator] = None
_allocator_lock = asyncio.Lock()


async def get_latency_allocator() -> LatencyAllocator:
    global _allocator
    async with _allocator_lock:
        if _allocator is None:
            _allocator = LatencyAllocator()
            await _allocator.start()
        return _allocator
