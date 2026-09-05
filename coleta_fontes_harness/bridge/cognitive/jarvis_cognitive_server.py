from __future__ import annotations
import base64
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from state_vector_daemon import StateVectorDaemon, get_system_state, get_semantic_graph
from multi_llm_router import CognitiveRouter, SYSTEM_PROMPT_PARA_INJETAR
from tool_execution_gatekeeper import ToolGatekeeper

class TalkRequest(BaseModel):
    audio_base64: Optional[str] = None
    text: Optional[str] = None
    fixture_id: Optional[str] = None

class TalkResponse(BaseModel):
    transcript: str
    reply_text: str
    route: str
    tool_result: Optional[Dict[str, Any]] = None
    pre_alert: Optional[Dict[str, Any]] = None
    tts_base64: Optional[str] = None
    state_snapshot: Dict[str, Any] = Field(default_factory=dict)

def mock_stt(audio_base64: Optional[str], fallback_text: Optional[str]) -> str:
    if fallback_text and fallback_text.strip(): return fallback_text.strip()
    if not audio_base64: return ""
    try:
        raw = base64.b64decode(audio_base64)
        return "status" if len(raw) < 8 else "analise a pressao de corners agora"
    except Exception:
        return "status"

def mock_tts(text: str) -> str:
    return base64.b64encode(f"TTS:{text[:180]}".encode("utf-8")).decode("ascii")

app = FastAPI(title="AURA Cognitive Voice Server", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[],
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$|^https?://(127\.0\.0\.1|localhost)(:\d+)?$", allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])
_daemon = StateVectorDaemon()
_router = CognitiveRouter()
_gate = ToolGatekeeper()
_started = False

@app.on_event("startup")
def _startup() -> None:
    global _started
    if not _started:
        _daemon.start(); _started = True

@app.on_event("shutdown")
def _shutdown() -> None:
    _daemon.stop()

@app.get("/api/health")
def health() -> Dict[str, Any]:
    st = get_system_state()
    return {"status": "ok", "service": "jarvis_cognitive_v3", "port": 8099, "state_ts": st.ts,
            "match_minute": st.match_minute, "pre_alert_ready": st.pre_alert_ready,
            "system_prompt_loaded": bool(SYSTEM_PROMPT_PARA_INJETAR)}

@app.get("/api/state")
def api_state() -> Dict[str, Any]:
    return {"state": get_system_state().to_dict(), "graph": get_semantic_graph().to_prompt_block()}

@app.post("/api/voice/talk", response_model=TalkResponse)
def voice_talk(req: TalkRequest) -> TalkResponse:
    transcript = mock_stt(req.audio_base64, req.text)
    if not transcript:
        raise HTTPException(status_code=400, detail="empty transcript")
    state = get_system_state(); graph = get_semantic_graph()
    routed = _router.route(transcript, state_vector=state, graph=graph)
    tool_result = routed.get("tool_result")
    if isinstance(tool_result, dict) and tool_result.get("status") == "blocked":
        reply = f"Gatekeeper bloqueou a acao: {tool_result.get('reason')}. Aguardando liberacao do administrador."
        return TalkResponse(transcript=transcript, reply_text=reply, route=str(routed.get("route") or "blocked"),
                            tool_result=tool_result, pre_alert=routed.get("pre_alert"), tts_base64=mock_tts(reply),
                            state_snapshot=state.to_dict())
    reply_text = str(routed.get("text") or "")
    pre = routed.get("pre_alert")
    if isinstance(pre, dict) and pre.get("pre_generated_audio_alert"):
        reply_text = f"{pre.get('text')} | {reply_text}".strip(" |")
    return TalkResponse(transcript=transcript, reply_text=reply_text, route=str(routed.get("route") or "glm"),
                        tool_result=tool_result if isinstance(tool_result, dict) else None,
                        pre_alert=pre if isinstance(pre, dict) else None, tts_base64=mock_tts(reply_text),
                        state_snapshot=state.to_dict())

@app.post("/api/voice/tool")
def voice_tool(payload: Dict[str, Any]) -> Dict[str, Any]:
    return _gate.execute(payload)



@app.post("/api/voice/tts")
def voice_tts(payload: dict):
    text = str((payload or {}).get("text") or "")
    return {"audio_base64": mock_tts(text), "text": text}

if __name__ == "__main__":
    import uvicorn
    _daemon.start()
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="info")
