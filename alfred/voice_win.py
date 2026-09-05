"""TTS Windows: Edge Neural pt-BR (Humberto) com pausas. Piper só se o Edge falhar."""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from . import paths

_BRIDGE = Path(__file__).resolve().parents[1] / "bridge"
if str(_BRIDGE) not in sys.path:
    sys.path.insert(0, str(_BRIDGE))

TTS_DIR = paths.DATA_ROOT / "tts"
MAX_SPEAK = 480
_PLAY_LOCK = threading.Lock()


def _sanitize(text: str) -> str:
    t = re.sub(r"[&|$;<>`]", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_SPEAK]


def _play_bytes(data: bytes) -> None:
    if not data:
        raise RuntimeError("áudio vazio")
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".wav" if data[:4] == b"RIFF" else ".mp3"
    path = TTS_DIR / f"utterance{suffix}"
    path.write_bytes(data)
    loc = str(path)
    if suffix == ".wav":
        import winsound
        winsound.PlaySound(loc, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        return
    ps = (
        "Add-Type -AssemblyName PresentationCore; "
        "$m = New-Object System.Windows.Media.MediaPlayer; "
        f"$m.Open([Uri]::new('{loc.replace(chr(39), '')}')); "
        "$m.Volume = 1; "
        "$n=0; while(-not $m.NaturalDuration.HasTimeSpan -and $n -lt 50){ Start-Sleep -Milliseconds 60; $n++ }; "
        "Start-Sleep -Milliseconds 280; $m.Play(); "
        "if($m.NaturalDuration.HasTimeSpan){ "
        "$ms=[Math]::Min(22000,[int]$m.NaturalDuration.TimeSpan.TotalMilliseconds + 650); "
        "Start-Sleep -Milliseconds $ms } else { Start-Sleep -Seconds 5 }"
    )
    subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=30,
    )


def _sapi_pt(text: str) -> dict:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = TTS_DIR / "sapi.txt"
    raw.write_text(text, encoding="utf-16")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "foreach($v in $s.GetInstalledVoices()){ "
        "$i=$v.VoiceInfo; "
        "if($i.Culture.Name -like 'pt*' -or $i.Name -match 'Maria|Heloisa|Daniel|Portuguese'){ "
        "$s.SelectVoice($i.Name); break } }; "
        f"$t = Get-Content -Raw -Encoding Unicode -LiteralPath '{raw}'; "
        "$s.Rate = -2; $s.Speak($t)"
    )
    p = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return {"ok": False, "engine": "SAPI", "error": (p.stderr or p.stdout or "sapi falhou")[:200]}
    return {"ok": True, "engine": "SAPI-pt", "chars": len(text),
            "nota": "fallback SAPI — qualidade inferior ao Edge Neural"}


def speak(text: str) -> dict:
    if sys.platform != "win32":
        return {"ok": False, "error": "TTS só no Windows"}
    safe = _sanitize(text)
    if not safe:
        return {"ok": False, "error": "texto vazio após sanitizar"}
    try:
        from jarvis.modules.neural_tts import humanize_for_speech, synthesize_mp3, available
        spoken = humanize_for_speech(safe)
        info = available()
        with _PLAY_LOCK:
            audio = synthesize_mp3(spoken, lang="pt-BR")
            _play_bytes(audio)
        return {
            "ok": True,
            "engine": info.get("engine") or "edge",
            "voice": info.get("voice") or "pt-BR-HumbertoNeural",
            "lang": "pt-BR",
            "chars": len(spoken),
            "format": "wav" if audio[:4] == b"RIFF" else "mp3",
        }
    except Exception as exc:
        fb = _sapi_pt(safe)
        fb["fallback_from"] = str(exc)[:180]
        return fb


def listen(seconds: int = 6) -> dict:
    """STT via SAPI. Pode estar BLOCKED se o reconhecimento Windows não estiver instalado."""
    if sys.platform != "win32":
        return {"ok": False, "blocked": True, "error": "STT só no Windows"}
    sec = max(3, min(int(seconds), 12))
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "try { "
        "$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
        "try { $r.SetInputToDefaultAudioDevice() } catch { throw }; "
        "foreach($c in [System.Globalization.CultureInfo]::GetCultures('SpecificCultures')){ "
        "if($c.Name -eq 'pt-BR'){ try { $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine($c) } catch {} ; break } }; "
        "$r.SetInputToDefaultAudioDevice(); "
        "$r.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar)); "
        f"$res = $r.Recognize([TimeSpan]::FromSeconds({sec})); "
        "if($res){ $res.Text } else { '' } "
        "} catch { 'BLOCKED:' + $_.Exception.Message }"
    )
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=sec + 15)
    except subprocess.TimeoutExpired:
        return {"ok": False, "blocked": True, "error": "timeout STT"}
    out = (p.stdout or "").strip()
    if out.startswith("BLOCKED:") or p.returncode != 0:
        err = out[:200] or (p.stderr or "")[:200]
        return {"ok": False, "blocked": True, "error": err,
                "nota": "O Windows nao tem reconhecedor SAPI (é normal neste PC). "
                        "No chat http://127.0.0.1:8777/chat clica FALAR e permite o microfone no Edge/Chrome."}
    if not out:
        return {"ok": True, "text": "", "nota": "nada reconhecido"}
    return {"ok": True, "text": out[:500], "engine": "SAPI", "lang": "pt-BR"}
