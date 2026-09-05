# -*- coding: utf-8 -*-
"""ALFRED local capabilities for Aura/Hermes.

No arbitrary shell, no deletion, no credentials and no background polling.
Actions are explicit, bounded, logged and require execute=True for side effects.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AURA_ROOT") or Path(__file__).resolve().parent).resolve()
DATA = ROOT / "data" / "alfred"
DATA.mkdir(parents=True, exist_ok=True)
MEMORY_FILE = DATA / "memory.json"
LOG_FILE = DATA / "actions.jsonl"
SCREEN_FILE = DATA / "screen_latest.png"
CAMERA_FILE = DATA / "camera_latest.jpg"
HOST = os.environ.get("ALFRED_HOST", "127.0.0.1")
PORT = int(os.environ.get("ALFRED_PORT", "8791"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("AURA_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "qwen3:8b"))
MAX_TASKS = 8
MAX_COMMAND_CHARS = 2000

_SAFE_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
    DATA,
]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _log(event: str, **fields: Any) -> None:
    row = {"ts": _now(), "event": event, **fields}
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_memory() -> dict[str, Any]:
    try:
        value = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"notes": [], "preferences": {}}
    except Exception:
        return {"notes": [], "preferences": {}}


def _save_memory(memory: dict[str, Any]) -> None:
    temp = MEMORY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(MEMORY_FILE)


def _under_allowed_root(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in _SAFE_ROOTS)
    except OSError:
        return False


def _safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", value).strip().strip(".")
    return value[:80] or "NovaPasta"


def _extract_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s,;]+", text, re.I)
    if not match:
        return None
    url = match.group(0).rstrip(".!?)\"'")
    parsed = urllib.parse.urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _split_tasks(command: str) -> list[str]:
    clean = re.sub(r"\s+", " ", command.strip())
    clean = re.sub(r"\b(alfred|aura|hermes)[,:]?\s*", "", clean, flags=re.I).strip()
    pieces = re.split(r"\s*(?:;|\bdepois\b|\bem seguida\b|\be também\b|\btamb[eé]m\b)\s*", clean, flags=re.I)
    out: list[str] = []
    for piece in pieces:
        piece = piece.strip(" ,")
        if not piece:
            continue
        # A single comma-separated command can contain several imperative tasks.
        comma_parts = [p.strip() for p in piece.split(",") if p.strip()]
        if len(comma_parts) > 1 and any(re.match(r"(?i)(cria|abra|abre|organiza|escreve|digita|toca|lembra|captura)", p) for p in comma_parts):
            out.extend(comma_parts)
        else:
            out.append(piece)
    return out[:MAX_TASKS]


def parse_command(command: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for text in _split_tasks(command[:MAX_COMMAND_CHARS]):
        low = text.lower()
        url = _extract_url(text)
        if re.search(r"(?i)organiza(?:r)? (?:a )?(?:minha )?area de trabalho|organizar desktop", text):
            tasks.append({"kind": "organize_desktop", "text": text})
        elif re.search(r"(?i)cria(?:r)? (?:uma )?pasta", text):
            match = re.search(r"(?i)pasta(?: chamada| denominada)?\s+[\"']?([^\"']+?)[\"']?$", text)
            name = _safe_name(match.group(1)) if match else "NovaPasta"
            tasks.append({"kind": "create_folder", "name": name, "text": text})
        elif re.search(r"(?i)(abre|abrir|pesquisa|pesquisar|navega|navegar)", text) and (url or "google" in low or "youtube" in low or "pesquis" in low):
            if not url and "youtube" in low:
                url = "https://www.youtube.com"
            elif not url:
                query = re.sub(r"(?i).*?(?:pesquisar|pesquisas?|google)\s*", "", text).strip(" .") or "pesquisa"
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            count_match = re.search(r"(?i)\b(\d+|uma|duas|dois|tr[eê]s|quatro|cinco)\s+(?:pesquisas?|p[aá]ginas?)\b", text)
            number_words = {"uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5}
            raw_count = count_match.group(1).lower() if count_match else "1"
            count = int(raw_count) if raw_count.isdigit() else number_words.get(raw_count, 1)
            count = min(count, 5)
            for offset in range(count):
                page_url = url
                if offset and "google.com/search?" in url:
                    page_url += "&start=" + str(offset * 10)
                tasks.append({"kind": "open_url", "url": page_url, "text": text, "sequence": offset + 1})
        elif re.search(r"(?i)(captura|tira|tire).*(tela|ecrã|ecra|screen)", text):
            tasks.append({"kind": "capture_screen", "text": text})
        elif re.search(r"(?i)(olha|veja|vê|camera|câmera|camara).*(camera|câmera|camara|mundo)", text):
            tasks.append({"kind": "capture_camera", "text": text})
        elif re.search(r"(?i)(escreve|digita|diga|responde).+", text):
            content = re.sub(r"(?i)^(?:escreve|digita|diga|responde)(?:\s+|:)+", "", text).strip()
            tasks.append({"kind": "type_text", "text": text, "content": content[:1500]})
        elif re.search(r"(?i)(lembra|memoriza|guarda|recorda)", text):
            note = re.sub(r"(?i)^(?:lembra|memoriza|guarda|recorda)(?:-te)?(?:\s+de|\s+que|:)?\s*", "", text).strip()
            tasks.append({"kind": "remember", "note": note[:500], "text": text})
        elif re.search(r"(?i)^(status|estado|saúde|saude)$", text.strip()):
            tasks.append({"kind": "status", "text": text})
        else:
            tasks.append({"kind": "unsupported", "text": text})
    return tasks


def _open_url(url: str, execute: bool) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "error": "URL bloqueada: apenas http/https"}
    if not execute:
        return {"ok": True, "dry_run": True, "action": "open_url", "url": url}
    try:
        if os.name == "nt":
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "action": "open_url", "url": url}
    except Exception as exc:
        return {"ok": False, "error": f"falha ao abrir URL: {exc}"}


def _create_folder(name: str, execute: bool) -> dict[str, Any]:
    target = Path.home() / "Desktop" / _safe_name(name)
    if not _under_allowed_root(target):
        return {"ok": False, "error": "destino fora da allowlist"}
    if not execute:
        return {"ok": True, "dry_run": True, "action": "create_folder", "path": str(target)}
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "action": "create_folder", "path": str(target)}


def _organize_desktop(execute: bool) -> dict[str, Any]:
    desktop = Path.home() / "Desktop"
    target = desktop / "Organizado_AURA"
    if not desktop.exists():
        return {"ok": False, "error": "Desktop não encontrado"}
    files = [p for p in desktop.iterdir() if p.is_file() and p.name.lower() not in {"desktop.ini"}]
    plan = [{"source": str(p), "destination": str(target / p.name)} for p in files[:100]]
    if not execute:
        return {"ok": True, "dry_run": True, "action": "organize_desktop", "count": len(plan), "plan": plan}
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for item in plan:
        source = Path(item["source"])
        destination = target / source.name
        if source.exists() and not destination.exists():
            shutil.move(str(source), str(destination))
            moved.append({"source": str(source), "destination": str(destination)})
    return {"ok": True, "action": "organize_desktop", "count": len(moved), "moved": moved}


def _capture_screen(execute: bool) -> dict[str, Any]:
    if not execute:
        return {"ok": True, "dry_run": True, "action": "capture_screen", "path": str(SCREEN_FILE)}
    try:
        import pyautogui  # type: ignore
        image = pyautogui.screenshot()
        image.save(SCREEN_FILE)
        return {"ok": True, "action": "capture_screen", "path": str(SCREEN_FILE)}
    except Exception as exc:
        return {"ok": False, "error": f"captura de tela indisponível: {exc}"}


def _capture_camera(execute: bool) -> dict[str, Any]:
    if not execute:
        return {"ok": True, "dry_run": True, "action": "capture_camera", "path": str(CAMERA_FILE)}
    try:
        import cv2  # type: ignore
        camera = cv2.VideoCapture(0)
        ok, frame = camera.read()
        camera.release()
        if not ok:
            return {"ok": False, "error": "câmara sem frame disponível"}
        cv2.imwrite(str(CAMERA_FILE), frame)
        return {"ok": True, "action": "capture_camera", "path": str(CAMERA_FILE)}
    except Exception as exc:
        return {"ok": False, "error": f"câmara indisponível: {exc}"}


def _type_text(content: str, execute: bool) -> dict[str, Any]:
    if not execute:
        return {"ok": True, "dry_run": True, "action": "type_text", "chars": len(content), "content_preview": content[:120]}
    try:
        import pyperclip  # type: ignore
        import pyautogui  # type: ignore
        pyperclip.copy(content)
        pyautogui.hotkey("ctrl", "v")
        return {"ok": True, "action": "type_text", "chars": len(content)}
    except Exception as exc:
        return {"ok": False, "error": f"escrita no foco indisponível: {exc}"}


def execute_task(task: dict[str, Any], execute: bool) -> dict[str, Any]:
    kind = task.get("kind")
    if kind == "open_url":
        return _open_url(str(task["url"]), execute)
    if kind == "create_folder":
        return _create_folder(str(task.get("name", "NovaPasta")), execute)
    if kind == "organize_desktop":
        return _organize_desktop(execute)
    if kind == "capture_screen":
        return _capture_screen(execute)
    if kind == "capture_camera":
        return _capture_camera(execute)
    if kind == "type_text":
        return _type_text(str(task.get("content", "")), execute)
    if kind == "remember":
        note = str(task.get("note", "")).strip()
        memory = _load_memory()
        if execute and note:
            memory.setdefault("notes", []).append({"ts": _now(), "text": note})
            memory["notes"] = memory["notes"][-200:]
            _save_memory(memory)
        return {"ok": True, "action": "remember", "dry_run": not execute, "note": note}
    if kind == "status":
        return {"ok": True, "action": "status", "root": str(ROOT), "memory_notes": len(_load_memory().get("notes", []))}
    return {"ok": False, "error": "comando não reconhecido", "text": task.get("text", "")}


def ask_qwen3(prompt: str) -> dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "És o cérebro local do ALFRED. Responde em português europeu, com clareza. Não inventes que executaste acções e não devolvas comandos de shell."},
            {"role": "user", "content": str(prompt)[:4000]},
        ],
        "stream": False,
        "keep_alive": "20m",
        "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 768, "num_gpu": 99},
    }
    try:
        request = urllib.request.Request(
            OLLAMA_URL + "/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            document = json.loads(response.read().decode("utf-8", errors="replace"))
        message = document.get("message") if isinstance(document, dict) else None
        content = message.get("content", "") if isinstance(message, dict) else ""
        return {"ok": bool(content), "model": OLLAMA_MODEL, "reply": str(content)}
    except Exception as exc:
        return {"ok": False, "model": OLLAMA_MODEL, "error": f"Ollama indisponível: {exc}"}


def run_command(command: str, execute: bool = False) -> dict[str, Any]:
    command = str(command or "").strip()
    if not command:
        return {"ok": False, "error": "comando vazio"}
    tasks = parse_command(command)
    results = []
    for task in tasks:
        result = execute_task(task, execute)
        _log("task", execute=execute, task=task, result=result)
        results.append({"task": task, "result": result})
    return {"ok": all(item["result"].get("ok") for item in results), "execute": execute, "tasks": results, "count": len(results)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "alfred", "port": PORT, "root": str(ROOT)})
        elif self.path == "/memory":
            self._send(200, _load_memory())
        elif self.path == "/model":
            self._send(200, {"ok": True, "backend": "ollama", "model": OLLAMA_MODEL, "url": OLLAMA_URL})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/ask":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 10000:
                    self._send(413, {"ok": False, "error": "pedido demasiado grande"})
                    return
                body = json.loads(self.rfile.read(size).decode("utf-8"))
                self._send(200, ask_qwen3(str(body.get("prompt", ""))))
            except Exception as exc:
                self._send(400, {"ok": False, "error": str(exc)})
            return
        if self.path != "/command":
            self._send(404, {"ok": False, "error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 10000:
                self._send(413, {"ok": False, "error": "pedido demasiado grande"})
                return
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            command = str(body.get("command", ""))
            execute = bool(body.get("execute", False))
            self._send(200, run_command(command, execute=execute))
        except Exception as exc:
            self._send(400, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        _log("http", client=self.client_address[0], message=fmt % args)


def serve() -> None:
    _log("start", host=HOST, port=PORT)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="ALFRED local command layer")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--command", "-c")
    parser.add_argument("--ask")
    parser.add_argument("--execute", action="store_true", help="execute side effects; without it, dry-run")
    args = parser.parse_args()
    if args.serve:
        serve()
        return 0
    if args.ask:
        result = ask_qwen3(args.ask)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 8
    if args.command:
        print(json.dumps(run_command(args.command, execute=args.execute), ensure_ascii=False, indent=2))
        return 0
    parser.error("use --serve, --ask ou --command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
