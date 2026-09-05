# hlc_clock.py
# AURA QUANT-X v12.6.17 / 12.8.x — Frente 1
# Hybrid Logical Clock + Vector Clock para Engine (porta 8765)
# Sincronização causal local-first entre Extension (N_E), Bridge (N_B) e Engine (N_G)
# Proteção de caminho quente com spin-lock de intenção < 1 µs

from __future__ import annotations

import time
import threading
import heapq
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import IntEnum


class NodeId(IntEnum):
    E = 0  # Extension
    B = 1  # Bridge
    G = 2  # Engine (self)


@dataclass(order=True)
class BufferedPacket:
    """Pacote congelado por estar no futuro relativo (> 35 ms)."""
    priority: Tuple[int, int, int]          # (pt, l, c) para ordenação
    receive_mono: float                     # monotonic time de chegada
    payload: Any = field(compare=False)
    hlc: "HLC" = field(compare=False)
    vc: Tuple[int, int, int] = field(compare=False)
    origin: NodeId = field(compare=False)


@dataclass
class HLC:
    """Hybrid Logical Clock: (pt, l, c)."""
    pt: int          # physical time em ms (epoch ou monotônico escalado)
    l: int           # componente lógico
    c: int           # contador de desempate

    def as_tuple(self) -> Tuple[int, int, int]:
        return (self.pt, self.l, self.c)

    def __str__(self) -> str:
        return f"HLC(pt={self.pt}, l={self.l}, c={self.c})"


class SpinLock:
    """
    Lock de caminho quente.
    Em Python usamos threading.Lock; a intenção de design é aquisição
    < 1 µs no caminho crítico (sem syscalls desnecessários, sem contention
    prolongada). Em produção real o equivalente Rust usaria AtomicBool
    com spin + exponential backoff curto.
    """
    __slots__ = ("_lock",)

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def acquire(self) -> None:
        self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> "SpinLock":
        self.acquire()
        return self

    def __exit__(self, *args: Any) -> None:
        self.release()


class HybridLogicalClockManager:
    """
    Gerencia VC = (c_E, c_B, c_G) e HLC = (pt, l, c) no nó Engine (N_G).
    Regras de mutação seguem exatamente a especificação da Teoria Reversa.
    """

    FUTURE_THRESHOLD_MS = 35          # pacotes com pt > local + 35 ms entram em buffer
    BUFFER_MAX_HOLD_MS = 48           # tempo máximo de congelamento antes do drop
    TICK_INTERVAL_S = 0.004           # 4 ms para varredura do buffer

    def __init__(self, node: NodeId = NodeId.G) -> None:
        self.node = node
        self._lock = SpinLock()                     # protege VC + HLC + buffer

        # Vector Clock: índices [E, B, G]
        self.vc: List[int] = [0, 0, 0]

        # HLC local
        now_ms = self._physical_time_ms()
        self.hlc = HLC(pt=now_ms, l=0, c=0)
        self._last_pt = now_ms

        # Buffer de pacotes futuros (min-heap por (pt, l, c))
        self._future_buffer: List[BufferedPacket] = []
        self._dropped_future = 0
        self._accepted = 0
        self._concurrent_merges = 0

        # Thread de varredura do buffer (daemon)
        self._running = True
        self._sweeper = threading.Thread(
            target=self._buffer_sweeper, name="hlc-buffer-sweeper", daemon=True
        )
        self._sweeper.start()

    # ------------------------------------------------------------------
    # Relógio físico
    # ------------------------------------------------------------------
    @staticmethod
    def _physical_time_ms() -> int:
        """Retorna tempo físico em milissegundos (monotônico escalado + epoch)."""
        return int(time.time() * 1000)

    # ------------------------------------------------------------------
    # Regras de mutação HLC — geração local
    # ------------------------------------------------------------------
    def _tick_local(self) -> HLC:
        """
        Ao gerar evento local:
            pt' = max(pt_local, pt_last)
            se pt' == pt_last → l' = l + 1
            senão → l' = 0
            c' incrementa (ou reseta se pt mudou)
        """
        pt_local = self._physical_time_ms()
        pt_prime = max(pt_local, self._last_pt)

        if pt_prime == self._last_pt:
            l_prime = self.hlc.l + 1
            c_prime = self.hlc.c + 1
        else:
            l_prime = 0
            c_prime = 0

        self.hlc = HLC(pt=pt_prime, l=l_prime, c=c_prime)
        self._last_pt = pt_prime
        return self.hlc

    # ------------------------------------------------------------------
    # Regras de mutação HLC — recepção de mensagem
    # ------------------------------------------------------------------
    def _merge_remote(self, hlc_m: HLC) -> HLC:
        """
        Ao receber mensagem com HLC_m:
            pt' = max(pt_local, pt_m, pt_last)
            casos de l' conforme especificação.
        """
        pt_local = self._physical_time_ms()
        pt_prime = max(pt_local, hlc_m.pt, self._last_pt)

        if pt_prime == pt_local and pt_prime == hlc_m.pt:
            l_prime = max(self.hlc.l, hlc_m.l) + 1
        elif pt_prime == pt_local:
            l_prime = self.hlc.l + 1
        elif pt_prime == hlc_m.pt:
            l_prime = hlc_m.l + 1
        else:
            l_prime = 0

        c_prime = self.hlc.c + 1
        self.hlc = HLC(pt=pt_prime, l=l_prime, c=c_prime)
        self._last_pt = pt_prime
        return self.hlc

    # ------------------------------------------------------------------
    # Vector Clock
    # ------------------------------------------------------------------
    def _update_vc_on_send(self) -> Tuple[int, int, int]:
        """Incrementa componente local e retorna cópia do VC."""
        idx = int(self.node)
        self.vc[idx] += 1
        return (self.vc[0], self.vc[1], self.vc[2])

    def _update_vc_on_receive(self, vc_msg: Tuple[int, int, int]) -> None:
        """
        VC_local[i] = max(VC_local[i], VC_msg[i])  ∀i
        depois incrementa o componente self.
        """
        for i in range(3):
            if vc_msg[i] > self.vc[i]:
                self.vc[i] = vc_msg[i]
        self.vc[int(self.node)] += 1

    # ------------------------------------------------------------------
    # Comparação causal
    # ------------------------------------------------------------------
    @staticmethod
    def happens_before(vc_a: Tuple[int, int, int], vc_b: Tuple[int, int, int]) -> bool:
        """Retorna True se vc_a < vc_b (sucede causalmente)."""
        less_or_eq = all(a <= b for a, b in zip(vc_a, vc_b))
        strictly_less = any(a < b for a, b in zip(vc_a, vc_b))
        return less_or_eq and strictly_less

    @staticmethod
    def concurrent(vc_a: Tuple[int, int, int], vc_b: Tuple[int, int, int]) -> bool:
        return not (
            HybridLogicalClockManager.happens_before(vc_a, vc_b)
            or HybridLogicalClockManager.happens_before(vc_b, vc_a)
        )

    # ------------------------------------------------------------------
    # API pública — gerar evento local
    # ------------------------------------------------------------------
    def generate_local_event(self, payload: Any = None) -> Dict[str, Any]:
        """
        Gera evento local, atualiza HLC e VC sob spin-lock.
        Retorna envelope pronto para serialização.
        """
        with self._lock:
            hlc = self._tick_local()
            vc = self._update_vc_on_send()
            self._accepted += 1
            return {
                "hlc": hlc.as_tuple(),
                "vc": vc,
                "origin": int(self.node),
                "payload": payload,
                "mono": time.monotonic(),
            }

    # ------------------------------------------------------------------
    # API pública — receber mensagem remota
    # ------------------------------------------------------------------
    def receive_remote(
        self,
        hlc_m: Tuple[int, int, int],
        vc_msg: Tuple[int, int, int],
        payload: Any,
        origin: int = NodeId.E,
    ) -> Optional[Dict[str, Any]]:
        """
        Processa mensagem remota.
        Se o pacote estiver > 35 ms no futuro → bufferiza.
        Caso contrário aplica merge e retorna envelope aceito.
        Retorna None se o pacote foi bufferizado (ainda não liberado).
        """
        hlc_remote = HLC(pt=hlc_m[0], l=hlc_m[1], c=hlc_m[2])
        now_ms = self._physical_time_ms()

        # Detecção de futuro relativo
        if hlc_remote.pt > now_ms + self.FUTURE_THRESHOLD_MS:
            with self._lock:
                pkt = BufferedPacket(
                    priority=hlc_remote.as_tuple(),
                    receive_mono=time.monotonic(),
                    payload=payload,
                    hlc=hlc_remote,
                    vc=vc_msg,
                    origin=NodeId(origin),
                )
                heapq.heappush(self._future_buffer, pkt)
            return None  # congelado

        # Caminho normal — merge sob spin-lock
        with self._lock:
            self._merge_remote(hlc_remote)
            self._update_vc_on_receive(vc_msg)

            if self.concurrent(tuple(self.vc), vc_msg):
                self._concurrent_merges += 1

            self._accepted += 1
            return {
                "hlc": self.hlc.as_tuple(),
                "vc": tuple(self.vc),
                "origin": origin,
                "payload": payload,
                "accepted_at": time.monotonic(),
            }

    # ------------------------------------------------------------------
    # Varredura do buffer de futuros
    # ------------------------------------------------------------------
    def _buffer_sweeper(self) -> None:
        """
        Thread daemon: a cada ~4 ms verifica pacotes bufferizados.
        Libera aqueles cujo pt já entrou na janela válida ou dropa após 48 ms.
        """
        while self._running:
            time.sleep(self.TICK_INTERVAL_S)
            now_ms = self._physical_time_ms()
            now_mono = time.monotonic()
            released: List[BufferedPacket] = []

            with self._lock:
                still_future: List[BufferedPacket] = []
                while self._future_buffer:
                    pkt = heapq.heappop(self._future_buffer)
                    age_ms = (now_mono - pkt.receive_mono) * 1000.0

                    if age_ms >= self.BUFFER_MAX_HOLD_MS:
                        self._dropped_future += 1
                        continue

                    if pkt.hlc.pt <= now_ms + self.FUTURE_THRESHOLD_MS:
                        released.append(pkt)
                    else:
                        still_future.append(pkt)

                for p in still_future:
                    heapq.heappush(self._future_buffer, p)

                for pkt in released:
                    self._merge_remote(pkt.hlc)
                    self._update_vc_on_receive(pkt.vc)
                    self._accepted += 1

    # ------------------------------------------------------------------
    # Observabilidade
    # ------------------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "hlc": self.hlc.as_tuple(),
                "vc": tuple(self.vc),
                "buffer_len": len(self._future_buffer),
                "dropped_future": self._dropped_future,
                "accepted": self._accepted,
                "concurrent_merges": self._concurrent_merges,
            }

    def shutdown(self) -> None:
        self._running = False
        if self._sweeper.is_alive():
            self._sweeper.join(timeout=0.5)


# ------------------------------------------------------------------
# Factory e helper de serialização
# ------------------------------------------------------------------
_manager: Optional[HybridLogicalClockManager] = None
_manager_lock = threading.Lock()


def get_hlc_manager() -> HybridLogicalClockManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = HybridLogicalClockManager(node=NodeId.G)
        return _manager


def envelope_from_raw(
    hlc_tuple: Tuple[int, int, int],
    vc_tuple: Tuple[int, int, int],
    payload: Any,
    origin: int = 0,
) -> Optional[Dict[str, Any]]:
    """Helper para o consumer da Engine receber pacotes já deserializados."""
    return get_hlc_manager().receive_remote(hlc_tuple, vc_tuple, payload, origin)
