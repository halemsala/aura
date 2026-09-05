# -*- coding: utf-8 -*-
"""
JARVIS Voice Router v1.2
Pânico → determinístico → LLM JSON → gates → execução → fala sempre.
Nunca toca em paper_trade / execution_allowed / Ollama kill.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Set, Tuple
from urllib.request import Request, urlopen

logger = logging.getLogger("aura.jarvis.router")

try:
    from bridge.jarvis.security.safe_executor import SAFE_EXECUTOR
except Exception:
    SAFE_EXECUTOR = None
try:
    from bridge.jarvis.vision.face_id_manager import VISION_MANAGER
except Exception:
    VISION_MANAGER = None

AUDIT_LOG = os.path.join("logs_supervisor", "aura_jarvis_actions.jsonl")
OLLAMA_URL = os.environ.get("AURA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
LLM_MODEL = os.environ.get("AURA_JARVIS_MODEL", "qwen2.5:3b-instruct")
FACE_VALID_MINUTES = 5
PANIC_SECONDS = 60
MAX_TYPE_LEN = 500

DANGEROUS_TOOLS = {"type_text", "click", "move_mouse", "press_key", "safe_delete"}
DESTRUCTIVE_TOOLS = {"safe_delete"}
ALLOWED_KEYS = {
    "enter", "esc", "escape", "tab", "space", "backspace", "delete",
    "up", "down", "left", "right", "home", "end", "pageup", "pagedown", "f5",
}
TOOL_ARGS = {
    "type_text": {"text"},
    "click": {"x", "y"},
    "move_mouse": {"x", "y"},
    "press_key": {"key"},
    "identify_user": set(),
    "safe_delete": {"path"},
}

SPOKEN = {
    "panic": "Modo pânico activo. Não mexo no sistema durante um minuto.",
    "whitelist": "Não tenho essa capacidade. Só uso ferramentas da lista.",
    "autorizo": "Essa acção precisa da tua autorização. Diz: autorizo.",
    "shield": "Escudo anti-aposta activo. Não interajo com casas de apostas.",
    "face": "Não confirmo o operador pela câmara. Identifica-te primeiro.",
    "args": "Parâmetros inválidos para esse comando.",
    "llm": "Não processei bem. Repete o pedido.",
    "executor": "Safe executor indisponível. Instala pyautogui se precisares de controlo.",
    "ok": "Feito.",
}


@dataclass
class RouteResult:
    spoken: str
    outcome: str = "none"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class VoiceRouter:
    def __init__(self) -> None:
        self._panic_until = 0.0
        self._face_seen_at = 0.0
        self._face_name: Optional[str] = None

    def route(self, transcript: str) -> RouteResult:
        transcript = (transcript or "").strip()
        authorized = self._has_autorizo(transcript)
        try:
            result = self._route_inner(transcript, authorized)
        except Exception as e:
            logger.exception("router fail")
            result = RouteResult(SPOKEN["llm"], "error", {"exception": str(e)[:200]})
        self._audit(transcript, result)
        return result

    def _route_inner(self, transcript: str, authorized: bool) -> RouteResult:
        if time.time() < self._panic_until:
            return RouteResult(SPOKEN["panic"], "blocked:panic")

        det = self._deterministic(transcript, authorized)
        if det is not None:
            return det

        data = self._llm_json(transcript)
        if data is None:
            return RouteResult(SPOKEN["llm"], "error", {"stage": "llm"})

        action = data.get("action")
        if action in (None, "none", "speak"):
            return RouteResult(self._clean_speak(data.get("speak")), "none")

        if action != "desktop_control":
            return RouteResult(SPOKEN["whitelist"], "blocked:whitelist", {"action": action})

        tool, args = data.get("tool"), data.get("args") or {}
        for gate in (
            lambda: self._gate_whitelist(tool, args),
            lambda: self._gate_autorizo(tool, authorized),
            lambda: self._gate_shield(tool),
            lambda: self._gate_face(tool),
        ):
            g = gate()
            if g:
                return g
        return self._execute(tool, args)

    def _deterministic(self, t: str, authorized: bool) -> Optional[RouteResult]:
        low = t.lower()
        if any(s in low for s in ("para de mexer", "pára de mexer", "aborta", "modo pânico", "modo panico")):
            self._panic_until = time.time() + PANIC_SECONDS
            return RouteResult(SPOKEN["panic"], "executed", {"panic_s": PANIC_SECONDS})

        if "quem está na câmara" in low or "quem esta na camera" in low or "quem está na câmera" in low:
            ok, name = self._ensure_identity(force=True)
            if ok:
                return RouteResult(f"Identifiquei {name}.", "executed", {"identity": name})
            return RouteResult("Não identifiquei ninguém.", "blocked:face", {"identity": name})

        if "status jarvis" in low or low.strip() in ("quem és tu", "quem es tu"):
            face = self._face_name if self._face_fresh() else "desconhecido"
            panic = "activado" if time.time() < self._panic_until else "desligado"
            return RouteResult(
                f"JARVIS activo. Operador: {face}. Pânico {panic}. paper_trade intacto.",
                "none",
                {"identity": face},
            )

        # atalhos simples sem LLM
        m = re.search(r"(?:escreve|digita)\s+(.+)$", t, re.I)
        if m:
            tool, args = "type_text", {"text": m.group(1)[:MAX_TYPE_LEN]}
            for gate in (
                lambda: self._gate_autorizo(tool, authorized),
                lambda: self._gate_shield(tool),
                lambda: self._gate_face(tool),
            ):
                g = gate()
                if g:
                    return g
            return self._execute(tool, args)

        return None

    def _llm_json(self, transcript: str) -> Optional[dict]:
        system = self._system_prompt()
        for attempt in (1, 2):
            body = {
                "model": LLM_MODEL,
                "format": "json",
                "stream": False,
                "options": {"num_predict": 256, "temperature": 0.2},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": transcript},
                ],
            }
            if attempt == 2:
                body["messages"].insert(
                    1,
                    {"role": "system", "content": "Responde APENAS JSON válido."},
                )
            try:
                data = json.dumps(body).encode("utf-8")
                req = Request(
                    OLLAMA_URL,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=25) as resp:
                    raw_json = json.loads(resp.read().decode("utf-8", "replace"))
                raw = (raw_json.get("message") or {}).get("content", "")
            except Exception as e:
                logger.warning("ollama fail attempt=%s err=%s", attempt, e)
                continue
            data = self._parse_json(raw)
            if data and self._valid_schema(data):
                return data
        return None

    def _parse_json(self, raw: str) -> Optional[dict]:
        if not raw:
            return None
        s = re.sub(r"```(?:json)?", "", raw).strip()
        start = s.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except Exception:
                        return None
        return None

    def _valid_schema(self, d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        if d.get("action") not in ("none", "speak", "desktop_control"):
            return False
        if not isinstance(d.get("speak", ""), str):
            return False
        if d["action"] == "desktop_control":
            if d.get("tool") not in TOOL_ARGS:
                return False
            args = d.get("args")
            if args is not None and not isinstance(args, dict):
                return False
        return True

    def _system_prompt(self) -> str:
        return f"""És o JARVIS do AURA QUANT-X. Responde SEMPRE em JSON:
{{"action":"none|speak|desktop_control","speak":"...","tool":"...","args":{{}}}}
Tools desktop_control: type_text, click, move_mouse, press_key, identify_user, safe_delete.
NUNCA trading, apostas, paper_trade, execution_allowed.
speak em português, curto. Máx type_text {MAX_TYPE_LEN} chars."""

    def _gate_whitelist(self, tool, args) -> Optional[RouteResult]:
        if tool not in TOOL_ARGS:
            return RouteResult(SPOKEN["whitelist"], "blocked:whitelist", {"tool": tool})
        extra = set((args or {}).keys()) - TOOL_ARGS[tool]
        if extra:
            return RouteResult(SPOKEN["args"], "blocked:whitelist", {"extra": sorted(extra)})
        if tool == "type_text":
            txt = (args or {}).get("text", "")
            if not isinstance(txt, str) or not (0 < len(txt) <= MAX_TYPE_LEN):
                return RouteResult(SPOKEN["args"], "blocked:whitelist")
        if tool == "press_key" and (args or {}).get("key") not in ALLOWED_KEYS:
            return RouteResult(SPOKEN["args"], "blocked:whitelist")
        return None

    def _gate_autorizo(self, tool, authorized: bool) -> Optional[RouteResult]:
        if tool in DESTRUCTIVE_TOOLS and not authorized:
            return RouteResult(SPOKEN["autorizo"], "blocked:autorizo", {"tool": tool})
        return None

    def _gate_shield(self, tool) -> Optional[RouteResult]:
        if tool not in DANGEROUS_TOOLS:
            return None
        if SAFE_EXECUTOR is None:
            return RouteResult(SPOKEN["executor"], "error")
        if not SAFE_EXECUTOR._is_active_window_safe():
            return RouteResult(SPOKEN["shield"], "blocked:shield", {"tool": tool})
        return None

    def _gate_face(self, tool) -> Optional[RouteResult]:
        if tool not in DANGEROUS_TOOLS:
            return None
        ok, name = self._ensure_identity()
        if not ok:
            return RouteResult(SPOKEN["face"], "blocked:face", {"identity": name})
        return None

    def _execute(self, tool, args) -> RouteResult:
        args = args or {}
        if tool == "identify_user":
            ok, name = self._ensure_identity(force=True)
            if ok:
                return RouteResult(f"Identifiquei {name}.", "executed", {"identity": name})
            return RouteResult("Não identifiquei ninguém.", "blocked:face", {"identity": name})
        if SAFE_EXECUTOR is None:
            return RouteResult(SPOKEN["executor"], "error")
        ok = False
        if tool == "type_text":
            ok = SAFE_EXECUTOR.type_text(args.get("text", ""))
        elif tool == "click":
            ok = SAFE_EXECUTOR.click(args.get("x"), args.get("y"))
        elif tool == "move_mouse":
            ok = SAFE_EXECUTOR.move_mouse(int(args["x"]), int(args["y"]))
        elif tool == "press_key":
            ok = SAFE_EXECUTOR.press_key(args.get("key", "enter"))
        elif tool == "safe_delete":
            path = args.get("path", "")
            SAFE_EXECUTOR.authorize_delete(path)
            ok = SAFE_EXECUTOR.safe_delete(path)
        if ok:
            return RouteResult(SPOKEN["ok"], "executed", {"tool": tool})
        return RouteResult("Acção falhou ou foi barrada.", "error", {"tool": tool})

    def _face_fresh(self) -> bool:
        return self._face_name is not None and (time.time() - self._face_seen_at) < FACE_VALID_MINUTES * 60

    def _ensure_identity(self, force: bool = False) -> Tuple[bool, str]:
        if not force and self._face_fresh():
            return True, self._face_name or ""
        if VISION_MANAGER is None:
            # sem visão: não bloqueia em ambientes sem câmara (fail-open controlado)
            if os.environ.get("AURA_JARVIS_FACE_REQUIRED", "0") == "1":
                return False, "sem_vision"
            self._face_name, self._face_seen_at = "OPERATOR", time.time()
            return True, "OPERATOR"
        res = VISION_MANAGER.capture_and_identify()
        good = {"ADMIN", "OPERATOR"}
        if getattr(VISION_MANAGER, "known_faces", None):
            good |= set(VISION_MANAGER.known_faces.keys())
        if res in good:
            self._face_name, self._face_seen_at = res, time.time()
            return True, res
        if res in ("NO_CAMERA", "COOLDOWN") and os.environ.get("AURA_JARVIS_FACE_REQUIRED", "0") != "1":
            self._face_name, self._face_seen_at = "OPERATOR", time.time()
            return True, "OPERATOR"
        return False, res

    @staticmethod
    def _has_autorizo(t: str) -> bool:
        return any(w in t.lower() for w in ("autorizo", "autorizado", "eu autorizo"))

    @staticmethod
    def _clean_speak(s: Any) -> str:
        s = (str(s) if s is not None else "Ok.").strip()
        if any(b in s.lower() for b in ("não posso ajudar", "nao posso ajudar")):
            return "Reformula o pedido."
        return s[:400]

    def _audit(self, transcript: str, result: RouteResult) -> None:
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG) or ".", exist_ok=True)
            entry = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "transcript": transcript[:200],
                "outcome": result.outcome,
                "spoken": result.spoken[:200],
                "detail": result.detail,
                "identity": self._face_name if self._face_fresh() else None,
            }
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("audit fail")


VOICE_ROUTER = VoiceRouter()


def process_voice_command(user_transcript: str) -> str:
    """API estável para jarvis_voice_server integrar."""
    return VOICE_ROUTER.route(user_transcript).spoken
