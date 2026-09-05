from __future__ import annotations

import asyncio
import unittest

from streaming_voice_pipeline import StreamingVoicePipeline


class FakeLLM:
    async def stream_generate(self, prompt: str):
        for token in ("primeira ", "frase. ", "segunda ", "frase!"):
            yield token


class FakeTTS:
    def __init__(self):
        self.phrases = []

    async def synthesize_chunk(self, text: str) -> bytes:
        self.phrases.append(text)
        return text.encode("utf-8")


class StreamingVoicePipelineV1272Tests(unittest.IsolatedAsyncioTestCase):
    async def test_sentences_are_queued_and_rendered_in_order(self):
        tts = FakeTTS()
        pipeline = StreamingVoicePipeline(stt=None, llm=FakeLLM(), tts=tts)
        await pipeline._process_and_speak("teste")
        await pipeline._tts_queue.join()
        self.assertEqual(tts.phrases, ["primeira frase.", "segunda frase!"])
        await pipeline.close()


if __name__ == "__main__":
    unittest.main()
