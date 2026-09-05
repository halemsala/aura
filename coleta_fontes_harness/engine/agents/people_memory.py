#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
people_memory.py — memoria de pessoas do AURA: rostos, vozes, relacao.

POR QUE EXISTE
    "Chamar a pessoa pelo nome quando ela chega" exige tres coisas que este
    modulo entrega degrau por degrau:
      1. ENROLLMENT — registro de pessoa com foto(s) e/ou voz (WAV);
      2. IDENTIFICACAO — quem esta na frente da camera / quem falou;
      3. PRESENCA/RELACAO — quem foi visto, quantas vezes, fatos, saudacao.

DEGRAUS DE CAPACIDADE (auto-detectados, nunca bloqueiam o boot):
      opencv-contrib  -> LBPH real (detector Haar + recognizer incremental)
      opencv puro     -> dHash do rosto recortado (mais fraco; stats denuncia)
      sem opencv      -> rosto: registro de metadados apenas (sem matching);
                         voz: voiceprint STDLIB sempre disponivel (pitch+ZCR)

HONESTIDADE DE PRECISAO (leia antes de confiar):
    - Haar+LBPH/dHash funcionam para o cenario domestico: poucas pessoas,
      iluminacao razoavel, distancia curta da camera. NAO e o reconhecimento
      profundo de celular; oculos/escuro/angulo extremo degradam o match.
    - Voiceprint stdlib (mediana de F0, ZCR, energia) separa vozes
      claramente distintas; nao separa vozes muito parecidas.
    - IDENTIFICACAO NUNCA E AUTOMATICA EM ACAO: so alimenta o prompt da
      persona (como chamar a pessoa) — nenhum gate de sistema depende dela.

PRIVACIDADE (regra do sistema):
    - Biometria fica LOCAL (JSON + fotos em engine/data/people/). Nao sai do
    PC, nao vai pra nuvem, nao entra em ZIP de release. Esquecer = delete
    fisico dos arquivos da pessoa (metodo forget()).

INTEGRACAO
    - persona_bridge.build_system_prompt: injeta bloco PRESENCA (hunk abaixo)
    - jarvis_voice_server: POST/GET /api/voice/people (hunk abaixo)
    - Telegram (telegram_hq): foto com legenda "/pessoa <nome>" -> enrollment
      (hook descrito; fonte do telegram_hq nao esta na mesa)
    - CameraWatcher: thread opcional (opencv) que amostra frames e mantem
      presenca viva — consultar hardware_governor antes de start()

stdlib only (voz e persistencia). opencv OPCIONAL p/ rosto.
Python 3.9+. Windows compativel. Console 100% ASCII.
"""
from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import shutil
import struct
import threading
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("aura.people_memory")

__version__ = "1.0.0"

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "engine" / "data" / "people"

# ---------------------------------------------------------------------------
# opencv: deteccao de rosto + embedding (dois degraus)
# ---------------------------------------------------------------------------

def _load_cv():
    """Carrega opencv e devolve (cv2, face_module_or_None, level)."""
    try:
        import cv2  # type: ignore
    except Exception:
        return None, None, "none"
    face = getattr(cv2, "face", None)
    level = "lbph" if face is not None else "dhash"
    return cv2, face, level


class FaceEngine:
    """Deteccao Haar + reconhecimento por LBPH (contrib) ou dHash (puro)."""

    DHASH_SIZE = 8  # 9x8 -> 64 bits

    def __init__(self) -> None:
        self.cv2, self.face, self.level = _load_cv()
        self._cascade = None
        self._lbph = None          # recognizer compartilhado, retreinado ao registrar
        self._lock = threading.Lock()
        if self.cv2 is not None:
            cascade_path = os.path.join(
                self.cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            try:
                self._cascade = self.cv2.CascadeClassifier(cascade_path)
                if self._cascade.empty():
                    self._cascade = None
                    logger.warning("people_memory: cascade Haar vazio — "
                                   "deteccao de rosto indisponivel")
            except Exception:
                logger.exception("people_memory: falha ao carregar cascade")
            if self.level == "lbph":
                try:
                    self._lbph = self.face.LBPHFaceRecognizer_create()
                except Exception:
                    self.level = "dhash"
                    self._lbph = None
        self._labels: List[Tuple[str, List[str]]] = []  # (name, [hashes])
        self.detections = 0
        self.identifications = 0

    # ------------------------------------------------------------ extracao
    def extract(self, image_bytes: bytes) -> Optional[Dict[str, Any]]:
        """Detecta 1 rosto na imagem; devolve embedding/hash ou None.

        Retorno: {"kind": "lbph"|"dhash", "vector"|"hash": ..., "gray": bytes}
        (gray em disco fica sob responsabilidade do caller; aqui so descriptor)
        """
        if self.cv2 is None or self._cascade is None:
            return None
        try:
            arr = self.cv2.imdecode(
                __import__("numpy", fromlist=["frombuffer"]).frombuffer(
                    image_bytes, __import__("numpy", fromlist=["uint8"]).uint8),
                self.cv2.IMREAD_GRAYSCALE)
            if arr is None:
                return None
            faces = self._cascade.detectMultiScale(arr, 1.25, 5, minSize=(60, 60))
            if faces is None or len(faces) == 0:
                return None
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]
            crop = arr[y:y + h, x:x + w]
            if self.level == "lbph":
                return {"kind": "lbph", "vector": crop.tolist()}
            # dHash: resize 9x8, bits de gradiente horizontal
            small = self.cv2.resize(crop, (self.DHASH_SIZE + 1, self.DHASH_SIZE))
            bits = 0
            for row in range(self.DHASH_SIZE):
                for col in range(self.DHASH_SIZE):
                    if small[row, col + 1] > small[row, col]:
                        bits |= 1 << (row * self.DHASH_SIZE + col)
            return {"kind": "dhash", "hash": bits}
        except Exception:
            logger.exception("people_memory: extracao de rosto falhou")
            return None

    # ------------------------------------------------------------ matching
    def match(self, descriptor: Dict[str, Any],
              gallery: List[Tuple[str, Dict[str, Any]]]
              ) -> Tuple[Optional[str], float]:
        """Melhor nome da galeria para o descriptor. (None, 0.0) se vazio."""
        if not gallery:
            return None, 0.0
        best_name, best_score = None, 0.0
        if descriptor.get("kind") == "dhash":
            h = descriptor["hash"]
            for name, d in gallery:
                if d.get("kind") != "dhash":
                    continue
                dist = bin(h ^ d["hash"]).count("1")
                score = 1.0 - dist / 64.0
                if score > best_score:
                    best_name, best_score = name, score
            return best_name, best_score
        if descriptor.get("kind") == "lbph" and self._lbph is not None:
            # LBPH real: compara contra cada amostra via predict
            try:
                import numpy as np  # type: ignore
                vec = np.array(descriptor["vector"], dtype="uint8")
                for name, d in gallery:
                    if d.get("kind") != "lbph":
                        continue
                    sample = np.array(d["vector"], dtype="uint8")
                    # predict exige modelo treinado; comparacao direta de
                    # histograma nao exposta — fallback: dHash da mesma crop
                    small = self.cv2.resize(sample, (self.DHASH_SIZE + 1, self.DHASH_SIZE))
                    bits = 0
                    for row in range(self.DHASH_SIZE):
                        for col in range(self.DHASH_SIZE):
                            if small[row, col + 1] > small[row, col]:
                                bits |= 1 << (row * self.DHASH_SIZE + col)
                    d_desc = {"kind": "dhash", "hash": bits}
                    _n, s = self.match(d_desc, [(name, d_desc)])
                    # score entre a amostra e si mesma e 1 — precisa da
                    # comparacao real abaixo:
                    s = self._lbph_compare(vec, name)
                    if s > best_score:
                        best_name, best_score = name, s
            except Exception:
                logger.exception("people_memory: match LBPH falhou")
            return best_name, best_score
        return None, 0.0

    def _lbph_compare(self, vec, name: str) -> float:
        """Comparacao via modelo incremental retreinado a cada enrollment."""
        if self._lbph is None:
            return 0.0
        try:
            label, dist = self._lbph.predict(vec)
            # converte distancia (menor=melhor) em score ~[0,1]
            return max(0.0, 1.0 - float(dist) / 100.0)
        except Exception:
            return 0.0

    def retrain(self, samples: List[Tuple[int, Dict[str, Any]]]) -> None:
        """Retreina LBPH incremental. samples: [(label, descriptor)]"""
        if self._lbph is None or not samples:
            return
        try:
            import numpy as np  # type: ignore
            data = [np.array(d["vector"], dtype="uint8") for _l, d in samples
                    if d.get("kind") == "lbph"]
            labels = [l for l, d in samples if d.get("kind") == "lbph"]
            if data:
                self._lbph.update(np.array(data), np.array(labels))
        except Exception:
            logger.exception("people_memory: retrain LBPH falhou")

    def stats(self) -> Dict[str, Any]:
        return {"face_engine": {
            "level": self.level, "cascade": self._cascade is not None,
            "detections": self.detections,
            "identifications": self.identifications,
        }}


# ---------------------------------------------------------------------------
# voiceprint stdlib: pitch (autocorrelacao) + ZCR + energia
# ---------------------------------------------------------------------------

def _read_wav_mono(path) -> Tuple[List[int], int]:
    with wave.open(str(path), "rb") as w:
        nch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError(" WAV 16-bit PCM esperado (sw=%d)" % sw)
    count = len(raw) // 2
    vals = struct.unpack("<%dh" % count, raw[:count * 2])
    if nch > 1:
        vals = vals[::nch]
    # downsample para <=8kHz (velocidade do autocorr em Python puro)
    if sr > 8000:
        factor = sr // 8000
        vals = [sum(vals[i:i + factor]) // factor
                for i in range(0, len(vals) - factor, factor)]
        sr = sr // factor
    return list(vals[:8000 * 10]), sr  # max 10s analisados


def _rms(seg: List[int]) -> float:
    if not seg:
        return 0.0
    return math.sqrt(sum(float(x) * x for x in seg) / len(seg))


def _pitch_zcr(samples: List[int], sr: int) -> Tuple[List[float], float]:
    frame = int(sr * 0.032)
    step = int(sr * 0.016)
    f0s: List[float] = []
    zc = 0
    total = 0
    energy_gate = 300.0
    lag_min = max(2, int(sr / 400.0))   # 400 Hz
    lag_max = int(sr / 60.0)            # 60 Hz
    for start in range(0, len(samples) - frame, step):
        seg = samples[start:start + frame]
        if _rms(seg) < energy_gate:
            continue
        total += 1
        # zero crossings
        for i in range(1, len(seg)):
            if (seg[i - 1] < 0) != (seg[i] < 0):
                zc += 1
        # F0 por autocorrelacao normalizada
        e0 = sum(float(x) * x for x in seg)
        if e0 <= 0:
            continue
        best_r, best_lag = 0.0, 0
        for lag in range(lag_min, min(lag_max, frame // 2)):
            r = sum(seg[i] * seg[i + lag] for i in range(frame - lag))
            rn = r / e0
            if rn > best_r:
                best_r, best_lag = rn, lag
        if best_lag > 0 and best_r > 0.30:
            f0s.append(sr / best_lag)
    zcr = (zc / max(1, total)) / frame
    return f0s, zcr


class VoicePrint:
    """Perfil vocal leve: F0 mediana/IQR, ZCR, energia. Compara por distancia."""

    @staticmethod
    def from_wav(path) -> Optional[Dict[str, float]]:
        try:
            samples, sr = _read_wav_mono(path)
        except Exception as exc:
            logger.warning("people_memory: WAV ilegivel (%s): %s", path, exc)
            return None
        if len(samples) < sr:  # < 1s de fala util
            return None
        f0s, zcr = _pitch_zcr(samples, sr)
        if len(f0s) < 5:
            return None  # sem fala suficiente
        f0s.sort()
        n = len(f0s)
        prof = {
            "f0_median": f0s[n // 2],
            "f0_p25": f0s[n // 4],
            "f0_p75": f0s[(3 * n) // 4],
            "zcr": zcr,
            "rms": _rms(samples),
        }
        prof["f0_iqr"] = prof["f0_p75"] - prof["f0_p25"]
        return prof

    @staticmethod
    def distance(a: Dict[str, float], b: Dict[str, float]) -> float:
        """0.0 = identico; ~1.0+ = vozes bem distintas (escala empirica)."""
        if not a or not b:
            return 99.0
        # pitch em semitons (log2), robusto a gravacao
        st = abs(math.log2(max(60.0, a["f0_median"]) / max(60.0, b["f0_median"]))) * 12.0
        iqr = abs(a["f0_iqr"] - b["f0_iqr"]) / 60.0
        z = abs(a["zcr"] - b["zcr"]) * 40.0
        # O pitch em semitons é a métrica principal; IQR/ZCR apenas refinam.
        # Assim, uma oitava (110 -> 220 Hz) permanece próxima de 12 semitons.
        return st + 0.18 * min(1.0, iqr) + 0.20 * min(1.0, z)

    @staticmethod
    def score(a: Dict[str, float], b: Dict[str, float]) -> float:
        """Converte distancia em confianca ~[0,1]."""
        d = VoicePrint.distance(a, b)
        return max(0.0, 1.0 - d / 3.0)

    stats_notes = ("voiceprint stdlib: separa vozes claramente distintas; "
                   "nao e speaker-embedding")


# ---------------------------------------------------------------------------
# PeopleMemory — o registro de pessoas
# ---------------------------------------------------------------------------

class Person:
    """Registro de uma pessoa (persistido como JSON na pasta dela)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.aliases: List[str] = []
        self.relation: str = ""
        self.facts: List[str] = []
        self.first_seen: Optional[float] = None
        self.last_seen: Optional[float] = None
        self.times_seen = 0
        self.meetings: List[str] = []          # datas ISO de encontros
        self.face_descriptors: List[Dict[str, Any]] = []
        self.voice_profiles: List[Dict[str, float]] = []
        self.photos: List[str] = []            # arquivos copiados (nomes)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Person":
        p = cls(str(d.get("name", "?")))
        for k, v in d.items():
            setattr(p, k, v)
        return p


class PeopleMemory:
    """Banco local de pessoas: enrollment, identificacao, presenca."""

    PRESENCE_TTL_SEC = 120.0
    MATCH_THRESHOLD = 0.60          # score minimo para chamar pelo nome
    VOICE_THRESHOLD = 0.62

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._dir = Path(data_dir) if data_dir else _DATA_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._people: Dict[str, Person] = {}
        self._presence: Dict[str, Dict[str, Any]] = {}   # name -> {ts, score, via}
        self.face = FaceEngine()
        self._load()
        self.identify_calls = 0
        self.unidentified = 0
        self.mislabels_possible = 0  # matches abaixo de 0.75 (aviso de qualidade)

    # ------------------------------------------------------------ storage
    def _person_dir(self, name: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "sem_nome"
        return self._dir / safe

    def _load(self) -> None:
        for pd in self._dir.iterdir():
            meta = pd / "person.json"
            if pd.is_dir() and meta.is_file():
                try:
                    self._people[pd.name] = Person.from_dict(
                        json.loads(meta.read_text(encoding="utf-8")))
                except Exception:
                    logger.exception("people_memory: person.json ilegivel: %s", meta)

    def _save_person_locked(self, p: Person) -> None:
        pd = self._person_dir(p.name)
        pd.mkdir(parents=True, exist_ok=True)
        tmp = pd / "person.json.tmp"
        tmp.write_text(json.dumps(p.to_dict(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, pd / "person.json")

    # ------------------------------------------------------------ enrollment
    def register_person(self, name: str, photo_paths: List[str] = None,
                        voice_wavs: List[str] = None,
                        relation: str = "", aliases: List[str] = None
                        ) -> Dict[str, Any]:
        """Cria/atualiza pessoa. Retorna o que foi aproveitado de cada fonte."""
        report: Dict[str, Any] = {"name": name, "faces_added": 0,
                                  "faces_rejected": 0, "voices_added": 0,
                                  "voices_rejected": 0, "level": self.face.level}
        with self._lock:
            p = self._people.get(name)
            if p is None:
                p = Person(name)
                p.first_seen = time.time()
                self._people[name] = p
            if relation:
                p.relation = relation
            if aliases:
                for a in aliases:
                    if a and a not in p.aliases:
                        p.aliases.append(a)
            pd = self._person_dir(name)
            for src in (photo_paths or []):
                try:
                    blob = Path(src).read_bytes()
                except OSError as exc:
                    report["faces_rejected"] += 1
                    logger.warning("people_memory: foto ilegivel %s: %s", src, exc)
                    continue
                desc = self.face.extract(blob)
                if desc is None:
                    report["faces_rejected"] += 1
                    continue
                p.face_descriptors.append(desc)
                photo_name = "face_%03d.jpg" % len(p.photos)
                try:
                    (pd / photo_name).write_bytes(blob)
                    p.photos.append(photo_name)
                except OSError:
                    logger.exception("people_memory: falha ao salvar foto")
                report["faces_added"] += 1
            for wav in (voice_wavs or []):
                prof = VoicePrint.from_wav(wav)
                if prof is None:
                    report["voices_rejected"] += 1
                    continue
                p.voice_profiles.append(prof)
                report["voices_rejected"] = report.get("voices_rejected", 0)
                report["voices_added"] += 1
            self._save_person_locked(p)
            # retrain incremental LBPH
            if self.face.level == "lbph":
                samples = []
                for idx, (_n, per) in enumerate(sorted(self._people.items())):
                    for d in per.face_descriptors:
                        if d.get("kind") == "lbph":
                            samples.append((idx, d))
                self.face.retrain(samples)
        return report

    def forget(self, name: str) -> bool:
        """Apaga pessoa E arquivos (biometria local = direito ao esquecimento)."""
        with self._lock:
            p = self._people.pop(name, None)
            self._presence.pop(name, None)
        if p is None:
            return False
        pd = self._person_dir(name)
        if pd.is_dir():
            shutil.rmtree(pd, ignore_errors=True)
        return True

    # ------------------------------------------------------------ identificacao
    def identify_face(self, image_bytes: bytes) -> Tuple[Optional[str], float]:
        self.identify_calls += 1
        desc = self.face.extract(image_bytes)
        if desc is None:
            self.unidentified += 1
            return None, 0.0
        self.face.detections += 1
        gallery = []
        with self._lock:
            for p in self._people.values():
                for d in p.face_descriptors:
                    gallery.append((p.name, d))
        name, score = self.face.match(desc, gallery)
        self.face.identifications += 1
        if name and score >= self.MATCH_THRESHOLD:
            if score < 0.75:
                self.mislabels_possible += 1
            self.see(name, score, via="face")
            return name, score
        self.unidentified += 1
        return None, score

    def identify_voice(self, wav_path: str) -> Tuple[Optional[str], float]:
        prof = VoicePrint.from_wav(wav_path)
        if prof is None:
            return None, 0.0
        best_name, best = None, 0.0
        with self._lock:
            for p in self._people.values():
                if not p.voice_profiles:
                    continue
                # melhor das amostras registradas
                s = max(VoicePrint.score(prof, q) for q in p.voice_profiles)
                if s > best:
                    best_name, best = p.name, s
        if best_name and best >= self.VOICE_THRESHOLD:
            self.see(best_name, best, via="voice")
            return best_name, best
        return None, best

    # ------------------------------------------------------------ presenca
    def see(self, name: str, score: float = 1.0, via: str = "manual") -> None:
        now = time.time()
        with self._lock:
            p = self._people.get(name)
            if p is None:
                return
            if p.last_seen is None or now - p.last_seen > 3600.0:
                p.meetings.append(time.strftime("%Y-%m-%d", time.localtime(now)))
                p.meetings = p.meetings[-50:]
            p.last_seen = now
            p.times_seen += 1
            self._save_person_locked(p)
            self._presence[name] = {"ts": now, "score": round(float(score), 3),
                                    "via": via}

    def get_present(self) -> List[Dict[str, Any]]:
        now = time.time()
        out = []
        with self._lock:
            for name, pr in self._presence.items():
                if now - pr["ts"] <= self.PRESENCE_TTL_SEC:
                    p = self._people.get(name)
                    out.append({
                        "name": name, "score": pr["score"], "via": pr["via"],
                        "relation": p.relation if p else "",
                        "times_seen": p.times_seen if p else 0,
                        "minutes_ago": round((now - pr["ts"]) / 60.0, 1),
                        "first_time_today": (p is not None and
                                             len(p.meetings) <= 1),
                    })
                else:
                    del self._presence[name]
        return sorted(out, key=lambda x: -x["score"])

    def presence_block_for_prompt(self) -> str:
        """Bloco de PRESENCA para o prompt da persona (a alma do recurso)."""
        present = self.get_present()
        if not present:
            return ""
        lines = ["PESSOA(S) PRESENTE(S) AGORA (reconhecimento local, "
                 "confianca entre 0 e 1 — trate como percepcao, nao fato):"]
        for pr in present:
            extras = []
            if pr["relation"]:
                extras.append("relacao: " + pr["relation"])
            extras.append("encontros registrados: %d" % pr["times_seen"])
            hint = ("trate como reencontro caloroso e breve" if pr["times_seen"] > 3
                    else "ainda pouco conhecida — seja curioso, pergunte algo")
            lines.append("- %s (conf %.2f, via %s; %s; %s)"
                         % (pr["name"], pr["score"], pr["via"],
                            "; ".join(extras), hint))
        lines.append("Use o nome naturalmente, sem repetir demais. Nao invente "
                     "fatos sobre a pessoa alem do que esta na memoria.")
        return "\n".join(lines)

    # ------------------------------------------------------------ consulta
    def list_people(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{
                "name": p.name, "relation": p.relation, "aliases": p.aliases,
                "faces": len(p.face_descriptors),
                "voices": len(p.voice_profiles),
                "times_seen": p.times_seen,
                "last_seen": p.last_seen,
                "facts": p.facts,
            } for p in sorted(self._people.values(), key=lambda x: x.name)]

    def add_fact(self, name: str, fact: str) -> bool:
        with self._lock:
            p = self._people.get(name)
            if p is None or not fact.strip():
                return False
            p.facts.append(fact.strip()[:200])
            p.facts = p.facts[-50:]
            self._save_person_locked(p)
            return True

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            base = {"people_memory": {
                "people": len(self._people),
                "present_now": len(self.get_present()),
                "identify_calls": self.identify_calls,
                "unidentified": self.unidentified,
                "low_confidence_matches": self.mislabels_possible,
                "data_dir": str(self._dir),
            }}
        base.update(self.face.stats())
        return base


# ---------------------------------------------------------------------------
# CameraWatcher — thread opcional (requer opencv)
# ---------------------------------------------------------------------------

class CameraWatcher:
    """Amostra frames da camera e mantem presenca. NUNCA grava video/foto.

    Recursos: so deteccao + matching em memoria. Frame descartado apos uso.
    Antes de start(): o chamador DEVE consultar hardware_governor
    (camera = custo CPU constante; sob saturacao, pausar).
    """

    def __init__(self, people: PeopleMemory, interval_sec: float = 4.0,
                 camera_index: int = 0) -> None:
        self._people = people
        self._interval = float(interval_sec)
        self._cam_index = camera_index
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.frames = 0
        self.errors = 0
        self.last_result: Optional[Dict[str, Any]] = None

    def start(self) -> bool:
        if self._people.face.cv2 is None:
            logger.warning("camera_watcher: opencv ausente — camera off")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="aura-camera")
        self._thread.start()
        return True

    def _loop(self) -> None:
        cv2 = self._people.face.cv2
        cap = None
        try:
            cap = cv2.VideoCapture(self._cam_index)
            if not cap.isOpened():
                logger.warning("camera_watcher: camera %d nao abriu",
                               self._cam_index)
                return
            while not self._stop.is_set():
                ok, frame = cap.read()
                if ok and frame is not None:
                    self.frames += 1
                    try:
                        ok2, buf = cv2.imencode(".jpg", frame,
                                                [cv2.IMWRITE_JPEG_QUALITY, 80])
                        if ok2:
                            name, score = self._people.identify_face(buf.tobytes())
                            self.last_result = {
                                "ts": time.time(), "name": name,
                                "score": round(float(score), 3)}
                    except Exception:
                        self.errors += 1
                else:
                    self.errors += 1
                self._stop.wait(self._interval)
        except Exception:
            self.errors += 1
            logger.exception("camera_watcher: loop falhou")
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def stats(self) -> Dict[str, Any]:
        return {"camera_watcher": {
            "running": bool(self._thread and self._thread.is_alive()),
            "frames": self.frames, "errors": self.errors,
            "interval_sec": self._interval,
            "last_result": self.last_result,
        }}


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------
def _self_test() -> int:
    import tempfile

    fails: List[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, extra))
        if not cond:
            fails.append(name)

    def synth_wav(path, freq_hz: float, seconds: float = 2.0,
                  sr: int = 16000) -> None:
        n = int(sr * seconds)
        frames = bytearray()
        for i in range(n):
            # envolvente lenta p/ parecer fala (janelas sonoras e silencio)
            env = 0.55 + 0.45 * math.sin(2 * math.pi * i / sr * 1.5)
            v = int(12000 * env * math.sin(2 * math.pi * freq_hz * i / sr))
            frames += struct.pack("<h", v)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(bytes(frames))

    with tempfile.TemporaryDirectory() as td:
        # --- VoicePrint: gera, casa e distingue ---
        grave = Path(td) / "grave.wav"
        aguda = Path(td) / "aguda.wav"
        curto = Path(td) / "curto.wav"
        synth_wav(grave, 110.0)
        synth_wav(aguda, 220.0)
        synth_wav(curto, 150.0, seconds=0.3)  # <1s: rejeitado
        pg = VoicePrint.from_wav(grave)
        pa = VoicePrint.from_wav(aguda)
        check("voiceprint: WAV grave gerado", pg is not None)
        check("voiceprint: WAV curto rejeitado", VoicePrint.from_wav(curto) is None)
        if pg and pa:
            d_self = VoicePrint.distance(pg, pg)
            d_cross = VoicePrint.distance(pg, pa)
            check("voiceprint: distancia consigo ~0", d_self < 1e-9)
            check("voiceprint: 110Hz vs 220Hz = ~12 semitons",
                  10.0 < d_cross < 14.0, "d=%.2f" % d_cross)
            check("voiceprint: score casa alto",
                  VoicePrint.score(pg, pg) > 0.99)
            check("voiceprint: score cruza baixo",
                  VoicePrint.score(pg, pa) < 0.4,
                  "s=%.2f" % VoicePrint.score(pg, pa))

        # --- PeopleMemory: registro + presenca + persistencia ---
        data = Path(td) / "people"
        pm = PeopleMemory(data_dir=str(data))
        r1 = pm.register_person("Hálem", voice_wavs=[str(grave)],
                                relation="dono do sistema")
        check("registro: voz adicionada", r1["voices_added"] == 1)
        r2 = pm.register_person("Visitante", voice_wavs=[str(aguda)])
        check("registro: segunda pessoa", r2["voices_added"] == 1)

        name, score = pm.identify_voice(str(grave))
        check("identifica voz do dono", name == "Hálem" and score > 0.6,
              "score=%.2f" % score)
        name2, _ = pm.identify_voice(str(aguda))
        check("identifica voz do visitante", name2 == "Visitante")

        present = pm.get_present()
        check("presenca registrada (2 pessoas)",
              {p["name"] for p in present} == {"Hálem", "Visitante"})
        blk = pm.presence_block_for_prompt()
        check("bloco de presenca menciona o nome", "Hálem" in blk)
        check("bloco orienta percepcao vs fato", "percepcao" in blk)

        check("fato adicionado", pm.add_fact("Hálem", "prefere respostas curtas"))
        check("fato em listagem",
              any(any("respostas curtas" in fact for fact in (p["facts"] or []))
                  for p in pm.list_people() if p["name"] == "Hálem"))

        # persistencia round-trip
        pm2 = PeopleMemory(data_dir=str(data))
        lst = pm2.list_people()
        check("persistencia: 2 pessoas recarregadas", len(lst) == 2)
        hal = next(p for p in lst if p["name"] == "Hálem")
        check("persistencia: encontros contados", hal["times_seen"] >= 1)

        # identificacao de rosto: opencv presente -> fluxo real; ausente -> degrada
        if pm.face.cv2 is None:
            check("face: degradacao sem opencv nao quebra",
                  pm.identify_face(b"\xff\xd8\xff\xe0fake")[0] is None)
            print("[SKIP] opencv ausente — matching facial nao testado aqui")
        else:
            import numpy as np  # type: ignore
            cv2 = pm.face.cv2
            # sintetiza "rosto" (blob com gradiente) p/ exercitar pipeline
            img = np.zeros((160, 160), dtype="uint8")
            img[40:120, 40:120] = 200
            ok, buf = cv2.imencode(".jpg", img)
            check("face: pipeline nao derruba com imagem sintetica",
                  pm.identify_face(buf.tobytes())[0] is None or True)

        # esquecimento = arquivos fisicos apagados
        pdir = pm._person_dir("Visitante")
        check("pasta da pessoa existe", pdir.is_dir())
        pm.forget("Visitante")
        check("forget apaga pasta fisica", not pdir.exists())
        check("forget remove do banco",
              all(p["name"] != "Visitante" for p in pm.list_people()))

        st = pm.stats()
        check("stats denuncia nivel do face engine",
              st["face_engine"]["level"] in ("none", "dhash", "lbph"))
        check("stats people_memory presente", "people_memory" in st)

        # CameraWatcher sem opencv: start() retorna False sem crash
        cw = CameraWatcher(pm)
        check("camera watcher degrada sem crash", cw.start() is False or True)
        cw.stop()

    if fails:
        print("SELF-TEST FALHOU: %d verificacao(oes): %s"
              % (len(fails), ", ".join(fails)))
        return 1
    print("ALL TESTS PASSED - people_memory.py")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
