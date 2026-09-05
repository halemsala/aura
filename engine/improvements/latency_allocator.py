# latency_allocator.py
# AURA QUANT-X v12.6.17 / 12.8.x — Frente 3
# Predictive Latency Budget Allocator — Porta 8099 (pipeline de voz)
# Controle M/D/1 preemptivo, tick de 8 ms, corte dinâmico de tokens Ollama
# Garante first_segment_ms ≤ 320 ms sem estourar VRAM

from __future__ import annotations

import time
import threading
import queue
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from collections import deque


# ------------------------------------------------------------------
# Constantes de orçamento (ms)
# ------------------------------------------------------------------
TOTAL_BUDGET_MS = 320.0
B_STT_NOMINAL = 90.0
B_LLM_NOMINAL = 140.0
B_TTS_NOMINAL = 70.0
B_OVERHEAD_NOMINAL = 20.0

TICK_MS = 8.0
RESIDUAL_STOP_THRESHOLD_MS = 95.0
EMA_ALPHA = 0.18
VRAM_HEADROOM_MIN_MB = 850.0
CHANNEL_CAPACITY = 3


class Priority(IntEnum):
    RISK_CMD = 0          # mais alta (preemptiva)
    NORMAL = 1
    BACKGROUND = 2


class AllocatorState(Enum):
    IDLE = "idle"
    STT_RUNNING = "stt_running"
    LLM_STREAMING = "llm_streaming"
    TTS_FIRST_CHUNK = "tts_first_chunk"
    COMPLETED = "completed"
    FORCE_STOPPED = "force_stopped"


@dataclass
class LatencyBudget:
    remaining_ms: float = TOTAL_BUDGET_MS
    stt_done: bool = False
    llm_tokens_emitted: int = 0
    llm_max_tokens_soft: int = 64
    llm_max_tokens_hard: int = 68
    tts_first_chunk_ready: bool = False
    gpu_vram_headroom_mb: float = 2048.0
    priority: Priority = Priority.NORMAL
    state: AllocatorState = AllocatorState.IDLE
    utterance_end_mono: float = 0.0
    first_segment_mono: Optional[float] = None
    text_buffer: str = ""
    tau_hat: float = 18.0                 # ms por token (EMA)
    stop_requested: bool = False


@dataclass(order=True)
class VoiceCommand:
    priority: int
    seq: int
    payload: Any = field(compare=False)
    enqueued_mono: float = field(compare=False, default_factory=time.monotonic)


class SpinLock:
    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "SpinLock":
        self._lock.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self._lock.release()


class PredictiveLatencyBudgetAllocator:
    """
    Allocator de orçamento de latência para o pipeline STT → LLM → TTS.
    Executa tick de 8 ms, mantém canal limitado de capacidade 3 com
    preempção de RISK_CMD, e corta o LLM quando residual < 95 ms.
    """

    def __init__(
        self,
        on_stop_llm: Optional[Callable[[], None]] = None,
        on_start_tts: Optional[Callable[[str], None]] = None,
        on_vram_query: Optional[Callable[[], float]] = None,
    ) -> None:
        self._lock = SpinLock()
        self.budget = LatencyBudget()
        self._cmd_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=CHANNEL_CAPACITY)
        self._seq = 0
        self._running = True
        self._tick_thread: Optional[threading.Thread] = None

        # Callbacks injetáveis (servidor de voz real)
        self.on_stop_llm = on_stop_llm or (lambda: None)
        self.on_start_tts = on_start_tts or (lambda text: None)
        self.on_vram_query = on_vram_query or (lambda: 2048.0)

        # Telemetria interna
        self._first_segment_latencies: Deque[float] = deque(maxlen=128)
        self._force_stops = 0
        self._preemptions = 0

        self._start_ticker()

    # ------------------------------------------------------------------
    # Ticker de 8 ms
    # ------------------------------------------------------------------
    def _start_ticker(self) -> None:
        def _loop() -> None:
            while self._running:
                t0 = time.monotonic()
                self._on_tick()
                elapsed = (time.monotonic() - t0) * 1000.0
                sleep_s = max(0.0, (TICK_MS - elapsed) / 1000.0)
                time.sleep(sleep_s)

        self._tick_thread = threading.Thread(
            target=_loop, name="latency-allocator-tick", daemon=True
        )
        self._tick_thread.start()

    def _on_tick(self) -> None:
        """Executado a cada ~8 ms. Atualiza residual e decide cortes."""
        with self._lock:
            if self.budget.state not in (
                AllocatorState.LLM_STREAMING,
                AllocatorState.STT_RUNNING,
            ):
                return

            if self.budget.utterance_end_mono <= 0.0:
                return

            elapsed_ms = (time.monotonic() - self.budget.utterance_end_mono) * 1000.0
            residual = TOTAL_BUDGET_MS - elapsed_ms
            self.budget.remaining_ms = residual

            # Atualiza VRAM
            try:
                self.budget.gpu_vram_headroom_mb = float(self.on_vram_query())
            except Exception:
                pass

            # Corte forçado por residual
            if residual <= RESIDUAL_STOP_THRESHOLD_MS and not self.budget.stop_requested:
                self._force_stop_and_tts()
                return

            # Corte por soft-limit de tokens
            if (
                self.budget.llm_tokens_emitted >= self.budget.llm_max_tokens_soft
                and not self.budget.stop_requested
            ):
                self._force_stop_and_tts()
                return

            # Proteção de VRAM
            if self.budget.gpu_vram_headroom_mb < VRAM_HEADROOM_MIN_MB:
                self.budget.llm_max_tokens_hard = max(
                    8, self.budget.llm_max_tokens_soft // 2
                )
                if self.budget.llm_tokens_emitted >= self.budget.llm_max_tokens_hard:
                    self._force_stop_and_tts()

    def _force_stop_and_tts(self) -> None:
        """Sinaliza stop ao LLM e dispara first-chunk TTS."""
        self.budget.stop_requested = True
        self.budget.state = AllocatorState.FORCE_STOPPED
        self._force_stops += 1
        text = self.budget.text_buffer.strip()
        if text:
            self.budget.tts_first_chunk_ready = True
            self.budget.first_segment_mono = time.monotonic()
            lat = (self.budget.first_segment_mono - self.budget.utterance_end_mono) * 1000.0
            self._first_segment_latencies.append(lat)
            try:
                self.on_stop_llm()
            except Exception:
                pass
            try:
                self.on_start_tts(text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # API de ciclo de vida de uma utterance
    # ------------------------------------------------------------------
    def notify_utterance_end(self, priority: Priority = Priority.NORMAL) -> None:
        """Chamado pelo STT quando o VAD fecha o utterance."""
        with self._lock:
            self.budget = LatencyBudget(
                remaining_ms=TOTAL_BUDGET_MS,
                stt_done=True,
                utterance_end_mono=time.monotonic(),
                priority=priority,
                state=AllocatorState.STT_RUNNING,
                tau_hat=self.budget.tau_hat,  # preserva EMA
            )
            if priority == Priority.RISK_CMD:
                self.budget.llm_max_tokens_soft = 32
                self.budget.llm_max_tokens_hard = 36

    def notify_llm_start(self) -> None:
        with self._lock:
            self.budget.state = AllocatorState.LLM_STREAMING
            self.budget.stt_done = True
            self._recompute_soft_limit()

    def notify_token(self, token_text: str, token_latency_ms: float) -> None:
        """
        Chamado a cada token emitido pelo Ollama (streaming).
        Atualiza EMA de τ̂ e o buffer de texto.
        """
        with self._lock:
            if self.budget.stop_requested:
                return

            self.budget.llm_tokens_emitted += 1
            self.budget.text_buffer += token_text

            # EMA do tempo por token
            self.budget.tau_hat = (
                EMA_ALPHA * token_latency_ms
                + (1.0 - EMA_ALPHA) * self.budget.tau_hat
            )
            self._recompute_soft_limit()

            if (
                self.budget.llm_tokens_emitted >= self.budget.llm_max_tokens_soft
                or self.budget.remaining_ms <= RESIDUAL_STOP_THRESHOLD_MS
            ):
                self._force_stop_and_tts()

    def _recompute_soft_limit(self) -> None:
        """
        T_soft = floor( (R - B_TTS - 15) / τ̂ )
        """
        residual = self.budget.remaining_ms
        usable = residual - B_TTS_NOMINAL - 15.0
        if usable <= 0 or self.budget.tau_hat <= 0:
            self.budget.llm_max_tokens_soft = 0
            self.budget.llm_max_tokens_hard = 4
            return

        t_soft = int(usable / self.budget.tau_hat)
        t_soft = max(0, t_soft)
        self.budget.llm_max_tokens_soft = t_soft
        self.budget.llm_max_tokens_hard = t_soft + 4

        if self.budget.priority == Priority.RISK_CMD:
            self.budget.llm_max_tokens_soft = min(self.budget.llm_max_tokens_soft, 28)
            self.budget.llm_max_tokens_hard = min(self.budget.llm_max_tokens_hard, 32)

    def notify_tts_first_chunk_done(self) -> None:
        with self._lock:
            self.budget.tts_first_chunk_ready = True
            self.budget.state = AllocatorState.COMPLETED
            if self.budget.first_segment_mono is None and self.budget.utterance_end_mono > 0:
                self.budget.first_segment_mono = time.monotonic()
                lat = (
                    self.budget.first_segment_mono - self.budget.utterance_end_mono
                ) * 1000.0
                self._first_segment_latencies.append(lat)

    # ------------------------------------------------------------------
    # Canal limitado com preempção (M/D/1)
    # ------------------------------------------------------------------
    def enqueue_command(self, payload: Any, priority: Priority = Priority.NORMAL) -> bool:
        """
        Enfileira comando de voz.
        Capacidade 3. RISK_CMD preempta (remove o de menor prioridade).
        """
        with self._lock:
            self._seq += 1
            cmd = VoiceCommand(
                priority=int(priority),
                seq=self._seq,
                payload=payload,
                enqueued_mono=time.monotonic(),
            )

            if self._cmd_queue.full():
                if priority == Priority.RISK_CMD:
                    try:
                        items: List[VoiceCommand] = []
                        while not self._cmd_queue.empty():
                            items.append(self._cmd_queue.get_nowait())
                        items.sort(key=lambda c: (c.priority, c.seq))
                        if items:
                            items.pop()
                            self._preemptions += 1
                        for it in items:
                            self._cmd_queue.put_nowait(it)
                        self._cmd_queue.put_nowait(cmd)
                        return True
                    except queue.Full:
                        return False
                else:
                    return False

            try:
                self._cmd_queue.put_nowait(cmd)
                return True
            except queue.Full:
                return False

    def dequeue_command(self, timeout: float = 0.05) -> Optional[VoiceCommand]:
        try:
            return self._cmd_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # Observabilidade e SLO
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            lats = list(self._first_segment_latencies)
            p95 = 0.0
            if lats:
                s = sorted(lats)
                idx = min(len(s) - 1, int(len(s) * 0.95))
                p95 = s[idx]
            return {
                "state": self.budget.state.value,
                "remaining_ms": round(self.budget.remaining_ms, 2),
                "tokens_emitted": self.budget.llm_tokens_emitted,
                "soft_limit": self.budget.llm_max_tokens_soft,
                "hard_limit": self.budget.llm_max_tokens_hard,
                "tau_hat_ms": round(self.budget.tau_hat, 2),
                "vram_headroom_mb": round(self.budget.gpu_vram_headroom_mb, 1),
                "stop_requested": self.budget.stop_requested,
                "force_stops": self._force_stops,
                "preemptions": self._preemptions,
                "first_segment_p95_ms": round(p95, 2),
                "queue_size": self._cmd_queue.qsize(),
            }

    def shutdown(self) -> None:
        self._running = False
        if self._tick_thread and self._tick_thread.is_alive():
            self._tick_thread.join(timeout=0.5)


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------
_allocator: Optional[PredictiveLatencyBudgetAllocator] = None
_alloc_lock = threading.Lock()


def get_latency_allocator(
    on_stop_llm: Optional[Callable[[], None]] = None,
    on_start_tts: Optional[Callable[[str], None]] = None,
    on_vram_query: Optional[Callable[[], float]] = None,
) -> PredictiveLatencyBudgetAllocator:
    global _allocator
    with _alloc_lock:
        if _allocator is None:
            _allocator = PredictiveLatencyBudgetAllocator(
                on_stop_llm=on_stop_llm,
                on_start_tts=on_start_tts,
                on_vram_query=on_vram_query,
            )
        return _allocator
