"""Grava o microfone do Windows (waveIn), preferindo o Realtek Array.

Não usa o browser. Não toca em ficheiros do sistema. Devolve WAV 16 kHz mono.
"""
from __future__ import annotations

import array
import ctypes
import os
import tempfile
import time
import wave
from ctypes import wintypes
from pathlib import Path

WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 0x00000001
WAVE_FORMAT_PCM = 1
MAXPNAMELEN = 32
PREFERRED = ("realtek", "conjunto de microfones", "microphone array", "array")


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_void_p),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("dwFormats", wintypes.DWORD),
        ("nChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


_winmm = ctypes.WinDLL("winmm")
_winmm.waveInGetNumDevs.restype = wintypes.UINT
_winmm.waveInGetDevCapsW.argtypes = [ctypes.c_uint, ctypes.POINTER(WAVEINCAPSW), wintypes.UINT]
_winmm.waveInOpen.argtypes = [
    ctypes.POINTER(wintypes.HANDLE), ctypes.c_uint, ctypes.POINTER(WAVEFORMATEX),
    ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
]
_winmm.waveInPrepareHeader.argtypes = [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT]
_winmm.waveInAddBuffer.argtypes = [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT]
_winmm.waveInStart.argtypes = [wintypes.HANDLE]
_winmm.waveInStop.argtypes = [wintypes.HANDLE]
_winmm.waveInReset.argtypes = [wintypes.HANDLE]
_winmm.waveInUnprepareHeader.argtypes = [wintypes.HANDLE, ctypes.POINTER(WAVEHDR), wintypes.UINT]
_winmm.waveInClose.argtypes = [wintypes.HANDLE]


def list_input_devices() -> list[dict]:
    n = int(_winmm.waveInGetNumDevs())
    out = []
    for i in range(n):
        caps = WAVEINCAPSW()
        err = _winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        if err != 0:
            continue
        out.append({"id": i, "name": str(caps.szPname).strip(), "channels": int(caps.nChannels)})
    return out


def unmute_capture() -> list[dict]:
    """Tira o mudo e põe volume 100% em todos os microfones activos."""
    out = []
    try:
        from comtypes import CLSCTX_ALL, CoInitialize
        from ctypes import POINTER, cast
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        CoInitialize()
        enumerator = AudioUtilities.GetDeviceEnumerator()
        coll = enumerator.EnumAudioEndpoints(1, 1)
        for i in range(coll.GetCount()):
            dev = coll.Item(i)
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            was_mute = bool(vol.GetMute())
            level = float(vol.GetMasterVolumeLevelScalar())
            if was_mute:
                vol.SetMute(0, None)
            if level < 0.85:
                vol.SetMasterVolumeLevelScalar(1.0, None)
            out.append({
                "id": dev.GetId(),
                "was_mute": was_mute,
                "was_vol": round(level, 3),
                "mute": bool(vol.GetMute()),
                "vol": round(float(vol.GetMasterVolumeLevelScalar()), 3),
            })
    except Exception as exc:
        out.append({"error": str(exc)[:180]})
    return out


def _boost(pcm: bytes, target: float = 0.12) -> bytes:
    """Normaliza PCM 16-bit para o Whisper ouvir microfones fracos."""
    rms = _rms_pcm16(pcm)
    if rms < 1e-5 or not pcm:
        return pcm
    gain = min(16.0, target / rms)
    if gain <= 1.05:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    boosted = array.array("h")
    for s in samples:
        v = int(s * gain)
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        boosted.append(v)
    return boosted.tobytes()


def pick_device(prefer: str = "realtek") -> dict:
    devices = list_input_devices()
    needle = (prefer or "realtek").casefold()
    for d in devices:
        if needle in d["name"].casefold():
            return d
    for token in PREFERRED:
        for d in devices:
            if token in d["name"].casefold():
                return d
    if devices:
        return devices[0]
    return {"id": WAVE_MAPPER, "name": "WAVE_MAPPER (predefinido Windows)", "channels": 1}


def _rms_pcm16(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += int(s) * int(s)
    return (acc / len(samples)) ** 0.5 / 32768.0


def _downsample(pcm: bytes, from_sr: int, to_sr: int = 16000) -> bytes:
    if from_sr == to_sr or not pcm:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if len(samples) < 2:
        return pcm
    try:
        import numpy as np
        x = np.asarray(samples, dtype=np.float32)
        n = max(1, int(round(len(x) * to_sr / from_sr)))
        idx = np.linspace(0, len(x) - 1, n)
        y = np.interp(idx, np.arange(len(x)), x)
        out = np.clip(y, -32768, 32767).astype(np.int16)
        return out.tobytes()
    except Exception:
        step = max(1, int(round(from_sr / to_sr)))
        trimmed = samples[::step]
        return array.array("h", trimmed).tobytes()


def _write_wav(path: Path, pcm: bytes, sr: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)


def record(seconds: float = 8.0, prefer: str = "realtek") -> dict:
    """Grava N segundos do microfone Windows. Devolve path WAV 16 kHz, rms, device."""
    if os.name != "nt":
        raise RuntimeError("gravação nativa só no Windows")
    sec = max(1.0, min(float(seconds), 15.0))
    unmute_info = unmute_capture()
    dev = pick_device(prefer)
    device_id = int(dev["id"])
    last_err = 0
    handle = wintypes.HANDLE()
    opened_sr = 0
    for sr in (16000, 44100, 48000):
        fmt = WAVEFORMATEX()
        fmt.wFormatTag = WAVE_FORMAT_PCM
        fmt.nChannels = 1
        fmt.nSamplesPerSec = sr
        fmt.wBitsPerSample = 16
        fmt.nBlockAlign = 2
        fmt.nAvgBytesPerSec = sr * 2
        fmt.cbSize = 0
        handle = wintypes.HANDLE()
        last_err = _winmm.waveInOpen(ctypes.byref(handle), device_id, ctypes.byref(fmt), None, None, 0)
        if last_err == 0:
            opened_sr = sr
            break
    if last_err != 0 or not handle:
        raise RuntimeError(f"waveInOpen falhou ({last_err}) no dispositivo {dev.get('name')}")

    nbytes = int(opened_sr * 2 * sec)
    buf = ctypes.create_string_buffer(nbytes)
    hdr = WAVEHDR()
    hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
    hdr.dwBufferLength = nbytes
    try:
        err = _winmm.waveInPrepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
        if err:
            raise RuntimeError(f"waveInPrepareHeader {err}")
        err = _winmm.waveInAddBuffer(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
        if err:
            raise RuntimeError(f"waveInAddBuffer {err}")
        err = _winmm.waveInStart(handle)
        if err:
            raise RuntimeError(f"waveInStart {err}")
        deadline = time.time() + sec + 1.5
        while time.time() < deadline:
            if hdr.dwFlags & WHDR_DONE:
                break
            time.sleep(0.03)
        _winmm.waveInStop(handle)
        _winmm.waveInReset(handle)
        recorded = int(hdr.dwBytesRecorded or 0)
        pcm = bytes(buf[:recorded] if recorded else buf)
        _winmm.waveInUnprepareHeader(handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
    finally:
        _winmm.waveInClose(handle)

    pcm16k = _downsample(pcm, opened_sr, 16000)
    raw_rms = _rms_pcm16(pcm16k)
    silent = raw_rms < 0.002
    if not silent:
        pcm16k = _boost(pcm16k)
    rms = _rms_pcm16(pcm16k)
    fd, tmp = tempfile.mkstemp(prefix="aura-mic-", suffix=".wav")
    os.close(fd)
    path = Path(tmp)
    _write_wav(path, pcm16k, 16000)
    return {
        "ok": True,
        "path": str(path),
        "rms": round(float(rms), 5),
        "raw_rms": round(float(raw_rms), 5),
        "silent": silent,
        "device": dev.get("name") or "Windows",
        "device_id": device_id,
        "seconds": sec,
        "sample_rate": 16000,
        "bytes": len(pcm16k),
        "unmute": unmute_info,
        "devices": list_input_devices(),
    }
