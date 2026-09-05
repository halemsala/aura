# -*- coding: utf-8 -*-
"""Vision Guard — FaceID em CPU (OpenCV Haar + LBPH opcional). 0 VRAM."""
from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("aura.vision")

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    cv2 = None
    np = None
    HAS_CV = False


class FaceIDManager:
    def __init__(self, data_dir: str = "engine/data/faces") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.known_faces = {}
        self.names = {0: "Desconhecido"}
        self.recognizer = None
        self.face_cascade = None
        self.last_check_time = 0.0
        if HAS_CV:
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
            except Exception as e:
                logger.warning("cascade fail: %s", e)
            self._load_and_train()
        else:
            logger.warning("OpenCV ausente — FaceID desactivado")

    def _load_and_train(self) -> None:
        faces, labels = [], []
        label_id = 1
        for img_path in self.data_dir.glob("*.jpg"):
            name = img_path.stem
            self.known_faces[name] = str(img_path)
            self.names[label_id] = name
            img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                faces.append(img)
                labels.append(label_id)
                label_id += 1
        if faces and hasattr(cv2, "face"):
            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create()
                self.recognizer.train(faces, np.array(labels))
                logger.info("LBPH treinado com %s amostra(s)", len(faces))
            except Exception as e:
                logger.warning("LBPH indisponivel: %s", e)
                self.recognizer = None
        elif faces:
            logger.info("Rostos em disco: %s (sem modulo cv2.face — so deteccao)", len(faces))

    def capture_and_identify(self) -> str:
        if not HAS_CV or self.face_cascade is None:
            return "NO_CAMERA"
        if time.time() - self.last_check_time < 30:
            return "COOLDOWN"
        self.last_check_time = time.time()
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        except Exception:
            cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return "NO_CAMERA"
        time.sleep(0.6)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return "CAPTURE_FAIL"
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) == 0:
            return "NO_FACE"
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        x, y, w, h = faces[0]
        roi = cv2.resize(gray[y : y + h, x : x + w], (200, 200))
        if self.recognizer is not None and len(self.names) > 1:
            label_id, confidence = self.recognizer.predict(roi)
            if confidence < 70:
                return self.names.get(label_id, "UNKNOWN_PERSON")
            return "UNKNOWN_PERSON"
        if self.known_faces:
            return "ADMIN"
        return "UNKNOWN_PERSON"


VISION_MANAGER = FaceIDManager()
