# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

ROOT = Path(r"C:\aura")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bridge"))
os.environ["AURA_TTS_ENGINE"] = "edge"
os.environ["KANTEIRO_NEURAL_VOICE"] = "pt-BR-HumbertoNeural"

fails = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    if not cond:
        fails.append(name)


from jarvis.modules.neural_tts import available, humanize_for_speech, synthesize_mp3
info = available()
check("engine edge", "edge" in str(info.get("engine") or "").lower() or info.get("voice") == "pt-BR-HumbertoNeural", str(info)[:180])
check("ready", bool(info.get("ready")), str(info.get("error")))
h = humanize_for_speech("Motor online. Agentes prontos.")
check("pausas", "..." in h, h)

audio = synthesize_mp3("Olá. Eu sou o Alfred. Voz em português do Brasil, com pausas naturais.")
check("audio", isinstance(audio, (bytes, bytearray)) and len(audio) > 400, f"bytes={len(audio) if audio else 0} head={audio[:4] if audio else None}")

import alfred.tools  # noqa
from alfred.router import chunk_to_tasks, is_system_control, _bare

check("ctrl lista", is_system_control("lista agentes"))
check("ctrl ativa", is_system_control("ative todos agentes"))
check("ctrl status", is_system_control("status do aura"))
check("ctrl voz", is_system_control("liga a voz"))
t = chunk_to_tasks("lista agentes") or []
check("task list", t and t[0].tool == "aura_agents_list", str(t))
t = chunk_to_tasks("ativa agentes") or []
check("task act", t and t[0].tool == "aura_agents_activate")
t = chunk_to_tasks("reinicia engine") or []
check("task rst", t and t[0].tool == "aura_restart")

print("FAILS", len(fails), fails)
sys.exit(1 if fails else 0)
