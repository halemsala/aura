# -*- coding: utf-8 -*-
"""AURA game watcher — segundo plano via ui/state (fonte real). Nao inventa fixture."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parents[1])
STATE_FILE = ROOT / "logs_supervisor" / "aura_game_watch.json"
EVENTS_FILE = ROOT / "logs_supervisor" / "aura_game_events.jsonl"
UI_STATE = os.environ.get("AURA_UI_STATE_URL", "http://127.0.0.1:8765/api/ui/state")
VOICE_TTS = os.environ.get("AURA_VOICE_TTS_URL", "http://127.0.0.1:8099/api/voice/tts")
VOICE_TALK = os.environ.get("AURA_VOICE_TALK_URL", "http://127.0.0.1:8099/api/voice/talk")

_lock = threading.Lock()
_thread = None
_stop = threading.Event()


def _ping_json(url: str, timeout: float = 2.5):
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace") or "{}")
    except Exception:
        return {}


def _post_json(url: str, payload: dict, timeout: float = 8.0) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        with urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _load():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "enabled": False,
        "voice_alerts": False,
        "last_fingerprint": "",
        "last_event": "",
        "last_ts": 0,
        "home": "",
        "away": "",
        "minute": "",
        "score_home": None,
        "score_away": None,
        "events_count": 0,
    }


def _save(st: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_event(ev: dict):
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _extract_view(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    snap = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
    view = snap.get("view") if isinstance(snap.get("view"), dict) else None
    if not view:
        view = data.get("view") if isinstance(data.get("view"), dict) else {}
    return view or {}


def _parse_score(view: dict):
    sh = view.get("score_home") or view.get("home_score") or view.get("goals_home")
    sa = view.get("score_away") or view.get("away_score") or view.get("goals_away")
    try:
        sh = int(sh) if sh is not None and str(sh).strip() != "" else None
    except Exception:
        sh = None
    try:
        sa = int(sa) if sa is not None and str(sa).strip() != "" else None
    except Exception:
        sa = None
    return sh, sa


def _fingerprint(view: dict) -> str:
    home = str(view.get("home") or view.get("home_team") or "")
    away = str(view.get("away") or view.get("away_team") or "")
    minute = str(view.get("minute") or view.get("clock") or "")
    sh, sa = _parse_score(view)
    corners = view.get("corners") or view.get("corner") or ""
    status = view.get("status") or view.get("period") or ""
    return f"{home}|{away}|{minute}|{sh}-{sa}|{corners}|{status}"


def _speak(text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    # tenta talk depois tts
    if not _post_json(VOICE_TALK, {"text": text, "message": text}):
        _post_json(VOICE_TTS, {"text": text, "message": text})


def _loop():
    while not _stop.is_set():
        try:
            st = _load()
            if not st.get("enabled"):
                time.sleep(2)
                continue
            data = _ping_json(UI_STATE)
            view = _extract_view(data)
            if not view:
                time.sleep(3)
                continue
            home = str(view.get("home") or view.get("home_team") or "")
            away = str(view.get("away") or view.get("away_team") or "")
            minute = str(view.get("minute") or view.get("clock") or "")
            sh, sa = _parse_score(view)
            fp = _fingerprint(view)
            prev_fp = st.get("last_fingerprint") or ""
            msgs = []
            if home and away and fp != prev_fp:
                # novo jogo / mudanca
                if not prev_fp or st.get("home") != home or st.get("away") != away:
                    msgs.append(f"Jogo activo: {home} x {away}" + (f" minuto {minute}" if minute else "") + ".")
                else:
                    prev_sh, prev_sa = st.get("score_home"), st.get("score_away")
                    if sh is not None and sa is not None and (prev_sh is not None) and (sh != prev_sh or sa != prev_sa):
                        msgs.append(f"Golo? Placar {home} {sh}-{sa} {away} ({minute}').")
                    elif minute and minute != str(st.get("minute") or ""):
                        # mudanca de minuto significativa a cada 5' ou status
                        try:
                            m0 = int(str(minute).replace("'", "").split("+")[0])
                            m1 = int(str(st.get("minute") or "0").replace("'", "").split("+")[0])
                            if abs(m0 - m1) >= 5:
                                msgs.append(f"Minuto {minute}'. {home} {sh if sh is not None else '-'}–{sa if sa is not None else '-'} {away}.")
                        except Exception:
                            pass
                    # corners delta se numerico
                    try:
                        c0 = view.get("corners_home") or view.get("home_corners")
                        c1 = view.get("corners_away") or view.get("away_corners")
                        if c0 is not None and c1 is not None:
                            pc0, pc1 = st.get("corners_home"), st.get("corners_away")
                            if pc0 is not None and (int(c0) != int(pc0) or int(c1) != int(pc1)):
                                msgs.append(f"Escanteios {c0}-{c1} ({home} x {away}, {minute}').")
                            st["corners_home"] = int(c0)
                            st["corners_away"] = int(c1)
                    except Exception:
                        pass

                for m in msgs:
                    ev = {"ts": time.time(), "text": m, "home": home, "away": away, "minute": minute}
                    _append_event(ev)
                    st["last_event"] = m
                    st["events_count"] = int(st.get("events_count") or 0) + 1
                    if st.get("voice_alerts"):
                        _speak(m)

                st["last_fingerprint"] = fp
                st["home"], st["away"], st["minute"] = home, away, minute
                st["score_home"], st["score_away"] = sh, sa
                st["last_ts"] = time.time()
                _save(st)
        except Exception:
            pass
        time.sleep(4)


def start_watch(voice_alerts: bool = False) -> str:
    global _thread
    st = _load()
    st["enabled"] = True
    st["voice_alerts"] = bool(voice_alerts)
    _save(st)
    _stop.clear()
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, name="aura-game-watch", daemon=True)
            _thread.start()
    return (
        f"Acompanhamento de jogo ACTIVO em segundo plano (ui/state). "
        f"Alertas de voz={'ON' if voice_alerts else 'OFF'}. "
        "Nao muda o ecra. Fonte: Engine :8765/api/ui/state (SokkerPRO via Desktop F2). "
        "Diz 'para de acompanhar' para parar."
    )


def stop_watch() -> str:
    st = _load()
    st["enabled"] = False
    _save(st)
    _stop.set()
    return "Acompanhamento de jogo parado."


def watch_status() -> str:
    st = _load()
    if not st.get("enabled"):
        return "Watcher OFF. Diz: acompanha o jogo  (ou: acompanha o jogo com voz)."
    fx = ""
    if st.get("home") and st.get("away"):
        fx = f" Live {st['home']} x {st['away']}"
        if st.get("minute"):
            fx += f" {st['minute']}'"
        sh, sa = st.get("score_home"), st.get("score_away")
        if sh is not None and sa is not None:
            fx += f" placar {sh}-{sa}"
        fx += "."
    last = st.get("last_event") or "sem eventos ainda"
    return (
        f"Watcher ON | voz={'ON' if st.get('voice_alerts') else 'OFF'} | eventos={st.get('events_count', 0)}."
        f"{fx} Ultimo: {last}"
    )


def recent_events(n: int = 8) -> str:
    if not EVENTS_FILE.exists():
        return "Sem eventos registados. Activa com: acompanha o jogo."
    try:
        lines = EVENTS_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()[-max(1, min(30, n)):]
        out = []
        for ln in lines:
            try:
                ev = json.loads(ln)
                out.append(str(ev.get("text") or ln)[:200])
            except Exception:
                out.append(ln[:200])
        return "Ultimos eventos:\n- " + "\n- ".join(out)
    except Exception as exc:
        return f"Erro a ler eventos: {exc}"


if __name__ == "__main__":
    print(start_watch(voice_alerts=False))
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print(stop_watch())
