"""
AURA QUANT-X :: Streaming Voice Pipeline (V23)
Chunked streaming + barge-in. Integra com STT/TTS existentes via Protocol.
"""
from __future__ import annotations
import asyncio
from typing import AsyncIterator, Optional, Protocol


class ISTT(Protocol):
    async def transcribe_stream(self, audio_queue: asyncio.Queue) -> AsyncIterator[str]: ...


class ILLM(Protocol):
    async def stream_generate(self, prompt: str) -> AsyncIterator[str]: ...


class ITTS(Protocol):
    async def synthesize_chunk(self, text: str) -> bytes: ...


class StreamingVoicePipeline:
    def __init__(self, stt: ISTT, llm: ILLM, tts: ITTS):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self._current_llm_task: Optional[asyncio.Task] = None
        self._current_tts_task: Optional[asyncio.Task] = None
        self._tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._tts_worker_task: Optional[asyncio.Task] = None
        self._interrupt_flag = asyncio.Event()

    async def start_listening(self, mic_audio_queue: asyncio.Queue):
        sentence_buffer = ""
        async for partial_word in self.stt.transcribe_stream(mic_audio_queue):
            if self._interrupt_flag.is_set():
                sentence_buffer = ""
                continue
            sentence_buffer += partial_word + " "
            if any(p in sentence_buffer for p in (".", "!", "?")):
                query = sentence_buffer.strip()
                sentence_buffer = ""
                if self._current_llm_task and not self._current_llm_task.done():
                    self._current_llm_task.cancel()
                self._interrupt_flag.clear()
                self._current_llm_task = asyncio.create_task(self._process_and_speak(query))

    async def _ensure_tts_worker(self) -> None:
        if self._tts_worker_task is None or self._tts_worker_task.done():
            self._tts_worker_task = asyncio.create_task(self._tts_worker())

    async def _tts_worker(self) -> None:
        while True:
            phrase = await self._tts_queue.get()
            try:
                if phrase is None:
                    return
                if not self._interrupt_flag.is_set() and phrase.strip():
                    await self._render_audio(phrase.strip())
            finally:
                self._tts_queue.task_done()

    async def _process_and_speak(self, query: str):
        try:
            await self._ensure_tts_worker()
            phrase_buffer = ""
            async for token in self.llm.stream_generate(query):
                if self._interrupt_flag.is_set():
                    return
                phrase_buffer += token
                if any(p in phrase_buffer for p in (".", "!", "?")):
                    phrase_to_speak = phrase_buffer.strip()
                    phrase_buffer = ""
                    await self._tts_queue.put(phrase_to_speak)
            if phrase_buffer.strip() and not self._interrupt_flag.is_set():
                await self._tts_queue.put(phrase_buffer.strip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[VOICE PIPELINE ERROR] {e}")

    async def close(self) -> None:
        """Encerra a fila sem interromper a frase atualmente em síntese."""
        if self._tts_worker_task and not self._tts_worker_task.done():
            await self._tts_queue.put(None)
            await self._tts_worker_task
        self._tts_worker_task = None

    async def _render_audio(self, text: str):
        await self.tts.synthesize_chunk(text)

    def user_spoke(self):
        """VAD externo: barge-in <50ms."""
        self._interrupt_flag.set()
