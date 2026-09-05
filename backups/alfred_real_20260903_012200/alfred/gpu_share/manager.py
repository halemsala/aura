"""Gestor central: workers registados, export do pacote, envio de jobs.
O Aura liga-se AO worker (outbound). Não abre a porta 8791 à LAN."""
import json
import secrets
import shutil
import time
import zipfile
from pathlib import Path

import requests

from .. import paths
from ..config import get_config

REG = paths.DATA_ROOT / "gpu_share" / "workers.json"
TOKEN_PATH = paths.DATA_ROOT / "gpu_share" / "local_token"
EXPORT_DIR = paths.DATA_ROOT / "gpu_share" / "export"


def _token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    t = secrets.token_urlsafe(24)
    TOKEN_PATH.write_text(t, encoding="utf-8")
    return t


def _load() -> list:
    if REG.exists():
        try:
            return json.loads(REG.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def _save(items: list) -> None:
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_workers() -> list:
    return _load()


def register_worker(host: str, port: int, label: str = "", token: str = "") -> dict:
    items = _load()
    entry = {"host": host, "port": int(port), "label": label or host,
             "token": token or _token(), "added": time.time()}
    items = [w for w in items if not (w["host"] == host and int(w["port"]) == int(port))]
    items.append(entry)
    _save(items)
    return {k: v for k, v in entry.items() if k != "token"} | {"token_set": True}


def worker_status(host: str, port: int, token: str = "") -> dict:
    tok = token or _token()
    url = f"http://{host}:{int(port)}/health"
    try:
        r = requests.get(url, headers={"X-Aura-Share-Token": tok}, timeout=5)
        return {"online": r.ok, "url": url, "body": r.json() if r.ok else r.text[:200]}
    except requests.RequestException as e:
        return {"online": False, "url": url, "error": str(e)[:200]}


def send_job(host: str, port: int, payload: dict, token: str = "") -> dict:
    tok = token or _token()
    url = f"http://{host}:{int(port)}/work"
    try:
        r = requests.post(url, json=payload, headers={"X-Aura-Share-Token": tok}, timeout=120)
        return {"http": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:400]}
    except requests.RequestException as e:
        return {"error": str(e)[:200]}


def export_pack() -> dict:
    """Cria ZIP para copiar para o outro PC. Não abre browser."""
    src_worker = Path(__file__).resolve().parent / "worker.py"
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    pack = EXPORT_DIR / "AURA_GPU_WORKER"
    if pack.exists():
        shutil.rmtree(pack)
    pack.mkdir(parents=True)
    shutil.copy2(src_worker, pack / "worker.py")
    token = _token()
    port = int(get_config().get("gpu_share_port") or 8795)
    pct = int(get_config().get("gpu_share_max_pct") or 60)
    bat = pack / "AURA_GPU_WORKER.bat"
    bat.write_text(
        "@echo off\r\n"
        "setlocal EnableExtensions\r\n"
        "cd /d \"%~dp0\"\r\n"
        "title AURA GPU WORKER\r\n"
        f"set AURA_GPU_SHARE_MAX_PCT={pct}\r\n"
        "where python.exe >nul 2>&1 || (echo Instala Python 3.11+ & pause & exit /b 2)\r\n"
        "echo Este PC vai oferecer ate "
        f"{pct}%% da VRAM ao Aura. Pausa automatica com jogos.\r\n"
        "echo Por defeito so localhost. Para LAN neste PC: AURA_GPU_WORKER.bat lan\r\n"
        "set LAN=\r\n"
        "if /I \"%~1\"==\"lan\" set LAN=--lan\r\n"
        f"python worker.py --token {token} --port {port} --max-pct {pct} %LAN%\r\n"
        "pause\r\n",
        encoding="utf-8",
    )
    (pack / "LEIA-ME.txt").write_text(
        "AURA GPU WORKER\n"
        "===============\n"
        "Isto NAO envia a tua VRAM para o outro PC. Corre inferência AQUI e devolve o texto/resultado.\n"
        f"Tecto: {pct}% da VRAM. Pausa se abrires um jogo ou o Windows precisar de memória.\n"
        "1. Copia esta pasta para o segundo PC.\n"
        "2. Corre AURA_GPU_WORKER.bat (localhost) ou AURA_GPU_WORKER.bat lan (rede local, só se quiseres).\n"
        "3. No Aura: Alfred, liga worker IP:8795\n"
        "O Aura central NÃO abre portas à LAN; é ele que liga ao worker.\n",
        encoding="utf-8",
    )
    zpath = EXPORT_DIR / "AURA_GPU_WORKER.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pack.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(pack)))
    return {"zip": str(zpath), "folder": str(pack), "port": port, "max_pct": pct,
            "nota": "copia o ZIP para o outro PC. LAN só se o dono desse PC passar 'lan'."}
