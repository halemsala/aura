"""Ponte de voz. O Alfred NÃO abre microfone por conta própria: recebe áudio/texto
do STT existente no Hermes e devolve texto para o TTS existente. Sem STT/TTS,
o Alfred continua funcional por texto e declara o componente em falta."""
import threading


class VoiceUnavailable(RuntimeError):
    pass


class AlfredVoice:
    def __init__(self, stt_fn=None, tts_fn=None, wake_prefixes=("alfred",)):
        # stt_fn: callable(audio) -> str ; tts_fn: callable(text) -> None
        # São fornecidos pelo Hermes quando existirem.
        self.stt_fn = stt_fn
        self.tts_fn = tts_fn
        self.wake_prefixes = tuple(p.casefold() for p in wake_prefixes)

    @property
    def available(self) -> dict:
        missing = [n for n, f in (("STT", self.stt_fn), ("TTS", self.tts_fn)) if f is None]
        return {"stt": self.stt_fn is not None, "tts": self.tts_fn is not None, "missing": missing}

    def transcribe(self, audio) -> str:
        if self.stt_fn is None:
            raise VoiceUnavailable("STT indisponível — o Alfred continua funcional por texto.")
        return str(self.stt_fn(audio)).strip()

    def speak(self, text: str) -> bool:
        if self.tts_fn is None:
            return False  # chamador mostra o texto; TTS declarado em falta em .available
        self.tts_fn(text)
        return True

    def is_for_alfred(self, text: str) -> bool:
        return (text or "").strip().casefold().startswith(self.wake_prefixes)

    def voice_loop(self, get_audio, stop_event: threading.Event, max_turns: int = 50,
                   on_state=None) -> dict:
        """Loop de voz EXPLICITAMENTE limitado: stop_event é OBRIGATÓRIO e há tecto max_turns.
        get_audio(timeout=...) -> audio|None (fornecido pelo Hermes).
        on_state(estado) é chamado com 'listening'/'thinking'/'speaking'/'stopped'
        para a UI mostrar o indicador. Nunca corre sem indicador nem sem forma de parar."""
        if get_audio is None or self.stt_fn is None:
            raise VoiceUnavailable("voz indisponível (STT em falta) — usa o chat por texto")
        if stop_event is None:
            raise VoiceUnavailable("stop_event obrigatório: nenhum microfone corre sem comando de parar")
        from .bridge import try_handle
        for _ in range(max_turns):
            if stop_event.is_set():
                break
            if on_state: on_state("listening")
            audio = get_audio(timeout=0.5)
            if audio is None:
                continue
            if on_state: on_state("thinking")
            try:
                text = self.transcribe(audio)
            except VoiceUnavailable:
                break
            if not text:
                continue
            if text.casefold() in ("alfred para", "para", "stop", "cancela voz"):
                break
            result = try_handle(text)
            if result is None:
                continue  # sem prefixo Alfred — o loop de voz só processa o Alfred
            if on_state: on_state("speaking")
            self.speak(result.get("reply", ""))
        if on_state: on_state("stopped")
        return {"stopped": True, "nota": "loop de voz terminado de forma controlada"}
