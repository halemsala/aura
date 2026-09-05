#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ponte de persona local e defensiva para o AURA.

O anexo forneceu apenas hunks de integração. Esta implementação de compatibilidade
mantém prompt, presença e memória como capacidades opt-in. Nenhuma câmera,
biometria ou gravação é ativada no import.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

__version__ = "1.1.0-compat"

DEFAULT_PERSONA_PROMPT = (
    "Você é AURA, um assistente operacional analítico. Seja claro, honesto "
    "sobre incertezas e nunca transforme análise em execução financeira real."
)


class PersonaBridge:
    """Constrói prompts e mantém presença local de forma opt-in."""

    def __init__(self, persona_prompt: str = DEFAULT_PERSONA_PROMPT,
                 people: Any = None, memory: Any = None,
                 enable_people: Optional[bool] = None):
        self.persona_prompt = str(persona_prompt or DEFAULT_PERSONA_PROMPT)
        self._lock = threading.RLock()
        self._memory = memory
        self._people = people
        if enable_people is None:
            enable_people = os.environ.get("AURA_ENABLE_PEOPLE_MEMORY", "0") == "1"
        if self._people is None and enable_people:
            try:
                from engine.agents.people_memory import PeopleMemory
                self._people = PeopleMemory()
            except Exception:
                self._people = None
        self._stats = {"prompts": 0, "remembered": 0,
                       "people_memory_active": self._people is not None}

    def presence_block_for_prompt(self) -> str:
        if self._people is None:
            return ""
        try:
            return str(self._people.presence_block_for_prompt() or "")
        except Exception:
            return ""

    def build_system_prompt(self, user_text: str = "", context: str = "",
                            extra: Optional[List[str]] = None) -> str:
        chunks = [self.persona_prompt]
        presence = self.presence_block_for_prompt()
        if presence:
            chunks.append(presence)
        if context:
            chunks.append("Contexto operacional:\n" + str(context)[:12000])
        if extra:
            chunks.extend(str(x)[:4000] for x in extra if x)
        prompt = "\n\n".join(chunks)
        with self._lock:
            self._stats["prompts"] += 1
        return prompt

    def build_prompt(self, *args, **kwargs) -> str:
        return self.build_system_prompt(*args, **kwargs)

    def remember(self, user_text: str = "", assistant_text: str = "",
                 session_id: str = "") -> Dict[str, Any]:
        """Registra somente presença nominal quando PeopleMemory estiver opt-in."""
        found = None
        if self._people is not None and user_text:
            try:
                for person in self._people.list_people():
                    name = str(person.get("name", ""))
                    if name and name.lower() in user_text.lower():
                        self._people.see(name, 1.0, via="conversa")
                        found = name
                        break
            except Exception:
                found = None
        with self._lock:
            self._stats["remembered"] += 1
        return {"ok": True, "person_seen": found, "session_id": str(session_id)}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"persona_bridge": dict(self._stats)}


def build_system_prompt(user_text: str = "", context: str = "",
                        bridge: Optional[PersonaBridge] = None) -> str:
    return (bridge or PersonaBridge()).build_system_prompt(user_text, context)


def _self_test() -> int:
    bridge = PersonaBridge(enable_people=False)
    prompt = bridge.build_system_prompt("bom dia", "paper trade")
    if "AURA" not in prompt or "paper trade" not in prompt:
        return 1
    if not bridge.remember("sem pessoa identificada").get("ok"):
        return 1
    if not bridge.stats()["persona_bridge"]["people_memory_active"]:
        print("ALL TESTS PASSED - persona_bridge.py")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
