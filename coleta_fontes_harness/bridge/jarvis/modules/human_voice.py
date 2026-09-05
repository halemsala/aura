# bridge/jarvis/modules/human_voice.py
"""
Human Voice Synthesizer v1.0
Edge-TTS com tratamento SSML para pausas e respiracao.
Requer: pip install edge-tts
"""
import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger("aura.voice.human")
VOICE = "pt-BR-HumbertoNeural"


class HumanVoiceSynthesizer:
    def __init__(self):
        self.temp_dir = Path("engine/data/temp_audio")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _text_to_ssml(self, text: str) -> str:
        text = text.replace("...", '<break time="400ms"/>')
        text = re.sub(r"\[respira\]", '<break time="600ms"/>', text, flags=re.IGNORECASE)
        text = text.replace(", ", ',<break time="200ms"/> ')
        return f"""
        <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="pt-BR">
            <prosody rate="1.05" pitch="medium">
                {text}
            </prosody>
        </speak>
        """.strip()

    async def synthesize(self, text: str, filename: str = "response.mp3") -> str:
        try:
            import edge_tts
        except ImportError:
            logger.error("edge-tts nao instalado.")
            return ""
        ssml = self._text_to_ssml(text)
        output_path = self.temp_dir / filename
        try:
            communicate = edge_tts.Communicate(ssml, VOICE)
            await communicate.save(str(output_path))
            return str(output_path)
        except Exception as e:
            logger.error("Erro no Edge-TTS: %s", e)
            return ""


VOICE_SYNTH = HumanVoiceSynthesizer()
