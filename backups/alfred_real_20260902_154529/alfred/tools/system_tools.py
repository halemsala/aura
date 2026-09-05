import hashlib, json, os, platform, shutil, signal, socket, subprocess, sys, time, zipfile
from pathlib import Path
from .. import paths
from ..config import get_config
from ..ollama_client import OllamaClient, OllamaUnavailable
from ..registry import ToolSpec, register
from ..validators import ValidationError
from .. import service as service_mod

import requests  # dependência base

PROJECT_ROOT = paths.PROJECT_ROOT


# ---------- system_status ----------
def _v0(args) -> dict:
    return {}

def system_status(args, ctx) -> dict:
    info = {"platform": platform.platform(), "python": sys.version.split()[0]}
    try:
        import psutil
        vm = psutil.virtual_memory()
        info.update(cpu_percent=psutil.cpu_percent(interval=0.2),
                    ram_used_pct=vm.percent, ram_total_gb=round(vm.total / 1e9, 1))
    except ImportError:
        info["nota_psutil"] = "psutil não instalado — CPU/RAM indisponíveis"
    try:
        d = shutil.disk_usage(str(PROJECT_ROOT.anchor or PROJECT_ROOT))
        info["disk_free_gb"] = round(d.free / 1e9, 1)
    except OSError:
        pass
    try:
        c = OllamaClient()
        info["ollama"] = {"online": True, "model_present": c.has_model(),
                          "models": c.installed_models()[:10]}
    except OllamaUnavailable as e:
        info["ollama"] = {"online": False, "error": str(e)[:200]}
    info["service_pid"] = service_mod.read_pid()
    return info

register(ToolSpec("system_status", system_status, _v0, risk="low", mutating=False,
                  summary="Estado do sistema, Ollama e serviço Alfred (só leitura)"))


# ---------- check_service ----------
def _v_check(args) -> dict:
    args = args or {}
    name = str(args.get("service") or "").strip().casefold()
    services = get_config().get("services", {})
    if name not in services:
        raise ValidationError(f"serviço '{name}' não está na allowlist: {sorted(services)}")
    return {"service": name, "spec": services[name]}

def check_service(args, ctx) -> dict:
    a = _v_check(args)
    s = a["spec"]
    if s.get("type") == "http":
        try:
            r = requests.get(s["url"], timeout=4)
            return {"service": a["service"], "online": r.status_code < 500, "status_code": r.status_code}
        except requests.RequestException as e:
            return {"service": a["service"], "online": False, "error": str(e)[:150]}
    sock = socket.socket()
    sock.settimeout(2)
    rc = sock.connect_ex(("127.0.0.1", int(s.get("port", 0))))
    sock.close()
    return {"service": a["service"], "online": rc == 0, "port": s.get("port")}

register(ToolSpec("check_service", check_service, _v_check, risk="low", mutating=False,
                  summary="Verifica saúde de serviço allowlisted (ollama/alfred/hermes)"))


# ---------- read_recent_log ----------
LOG_ROOTS = [paths.DATA_ROOT, PROJECT_ROOT / "logs", PROJECT_ROOT / "data" / "logs"]

def _v_log(args) -> dict:
    args = args or {}
    name = str(args.get("file") or "alfred.log")
    p = Path(name)
    if p.is_absolute():
        p = Path(os.path.realpath(p))
        if not any(str(p).casefold().startswith(str(r.resolve()).casefold()) for r in LOG_ROOTS):
            raise ValidationError("caminho de log fora da allowlist")
    else:
        for root in LOG_ROOTS:
            cand = root / p
            if cand.is_file():
                p = cand
                break
        else:
            raise ValidationError("log não encontrado nos directórios permitidos")
    n = max(1, min(int(args.get("lines", 40) or 40), 200))
    return {"path": p, "lines": n}

def read_recent_log(args, ctx) -> dict:
    a = _v_log(args)
    lines = a["path"].read_text(encoding="utf-8", errors="replace").splitlines()[-a["lines"]:]
    return {"file": str(a["path"]), "lines": lines}

register(ToolSpec("read_recent_log", read_recent_log, _v_log, risk="low", mutating=False,
                  summary="Lê últimas N linhas de log allowlisted"))


# ---------- run_python_compile ----------
def _v_compile(args) -> dict:
    raw = str((args or {}).get("path") or "")
    p = Path(os.path.realpath(Path(raw).expanduser()))
    root = Path(os.path.realpath(PROJECT_ROOT))
    if not str(p).casefold().startswith(str(root).casefold()):
        raise ValidationError("só compilo ficheiros dentro do projecto")
    if p.suffix != ".py":
        raise ValidationError("só ficheiros .py")
    if not p.is_file():
        raise ValidationError("ficheiro não existe")
    return {"path": p}

def run_python_compile(args, ctx) -> dict:
    p = _v_compile(args)["path"]
    import py_compile
    try:
        py_compile.compile(str(p), doraise=True)
        return {"ok": True, "file": str(p)}
    except py_compile.PyCompileError as e:
        return {"ok": False, "file": str(p), "error": str(e)[:500]}

register(ToolSpec("run_python_compile", run_python_compile, _v_compile, risk="low", mutating=False,
                  summary="Compila (py_compile) um .py do projecto — NÃO executa código"))


# ---------- create_checkpoint / restore_checkpoint ----------
CKPT_INCLUDE = [PROJECT_ROOT / "alfred", PROJECT_ROOT / "config", PROJECT_ROOT / "tests",
                PROJECT_ROOT / "requirements-alfred.txt"]
CKPT_EXCLUDE_DIRS = {"__pycache__", ".git", "venv", ".venv", "node_modules"}

def create_checkpoint(args, ctx) -> dict:
    if ctx.dry():
        return {"dry_run": True, "nota": "checkpoint não criado (dry-run)"}
    ts = time.strftime("%Y%m%d-%H%M%S")
    zp = paths.CHECKPOINTS_DIR / f"ckpt-{ts}.zip"
    manifest = {"created": ts, "files": []}
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for base in CKPT_INCLUDE:
            if not base.exists():
                continue
            if base.is_file():
                z.write(base, arcname=str(base.relative_to(PROJECT_ROOT)))
                continue
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in CKPT_EXCLUDE_DIRS]
                for fn in filenames:
                    fp = Path(dirpath) / fn
                    try:
                        if fp.stat().st_size > 5_000_000:
                            continue
                        arc = fp.relative_to(PROJECT_ROOT)
                        z.write(fp, arcname=str(arc))
                        manifest["files"].append({"f": str(arc), "sha": _sha(fp)})
                    except OSError:
                        continue
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return {"checkpoint": str(zp), "files": len(manifest["files"]), "size_bytes": zp.stat().st_size}

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

register(ToolSpec("create_checkpoint", create_checkpoint, _v0, risk="low", mutating=True,
                  summary="Cria checkpoint (zip + manifest) do código do Alfred/config/testes"))


def _v_restore(args) -> dict:
    target = str((args or {}).get("checkpoint") or "")
    p = paths.CHECKPOINTS_DIR / Path(target).name if target else None
    if not p or not p.exists():
        zps = sorted(paths.CHECKPOINTS_DIR.glob("ckpt-*.zip"))
        if not zps:
            raise ValidationError("não existem checkpoints")
        p = zps[-1]
    return {"zip": p}

def restore_checkpoint(args, ctx) -> dict:
    a = _v_restore(args)
    if ctx.dry():
        return {"dry_run": True, "checkpoint": str(a["zip"]), "nota": "nada restaurado (dry-run)"}
    from ..checkpoint_cli import restore_zip
    return restore_zip(a["zip"])

register(ToolSpec("restore_checkpoint", restore_checkpoint, _v_restore, risk="high", mutating=True,
                  sensitive=True,
                  summary="Restaura último checkpoint (FERRAMENTA SENSÍVEL: AUTORIZO + execution_allowed/token)"))


# ---------- restart_service ----------
def _v_restart(args) -> dict:
    args = args or {}
    name = str(args.get("service") or "").strip().casefold()
    cfg = get_config()
    if name != "alfred" and "restart_cmd" not in cfg.get("services", {}).get(name, {}):
        raise ValidationError(f"'{name}' sem restart_cmd na allowlist (só 'alfred' tem reinício embutido)")
    return {"service": name}

def restart_service(args, ctx) -> dict:
    a = _v_restart(args)
    if ctx.dry():
        return {"dry_run": True, "nota": "serviço não reiniciado (dry-run)"}
    cfg = get_config()
    if a["service"] == "alfred":
        pid = service_mod.read_pid()
        if pid and service_mod.is_running(pid):
            try:
                os.kill(pid, 9 if os.name == "nt" else signal.SIGTERM)
            except OSError:
                pass
            time.sleep(1.0)
        kwargs = {"cwd": str(PROJECT_ROOT)}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, "-m", "alfred.api",
                          "--host", cfg["host"], "--port", str(cfg["port"])], **kwargs)
        return {"restarted": True, "nota": "a resposta HTTP pode não chegar — confirma com /health"}
    cmd = get_config()["services"][a["service"]]["restart_cmd"]
    if not isinstance(cmd, list) or not all(isinstance(x, str) for x in cmd):
        raise ValidationError("restart_cmd malformado (deve ser lista de strings, sem shell)")
    subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
    return {"restarted": True, "service": a["service"]}

register(ToolSpec("restart_service", restart_service, _v_restart, risk="high", mutating=True,
                  sensitive=True,
                  summary="Reinicia apenas serviço allowlisted (alfred por PID registado; sem shell arbitrário)"))


# ---------- technical_diagnose ----------
def technical_diagnose(args, ctx) -> dict:
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    report["system"] = system_status({}, ctx)
    svc = {}
    for name in sorted(get_config().get("services", {})):
        try:
            svc[name] = check_service({"service": name}, ctx)
        except ValidationError as e:
            svc[name] = {"error": str(e)}
    report["services"] = svc
    avail = {}
    import importlib.util
    for mod in ("pyautogui", "pyperclip", "PIL", "cv2", "psutil", "fastapi"):
        avail[mod] = importlib.util.find_spec(mod) is not None
    report["optional_deps"] = avail
    report["checkpoints"] = len(list(paths.CHECKPOINTS_DIR.glob("ckpt-*.zip")))
    try:
        a = _v_log({"file": "alfred.log", "lines": 20})
        report["recent_log_tail"] = a["path"].read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
    except ValidationError:
        report["recent_log_tail"] = []
    problems = []
    if not report["system"].get("ollama", {}).get("online"):
        problems.append("Ollama offline — conversação e planeamento LLM indisponíveis")
    elif not report["system"]["ollama"].get("model_present"):
        problems.append(f"modelo {get_config()['model']} AUSENTE — não há fallback automático")
    if not avail["pyautogui"]:
        problems.append("pyautogui ausente — type_text indisponível")
    if not avail["PIL"]:
        problems.append("Pillow ausente — capture_screen indisponível")
    if not avail["cv2"]:
        problems.append("OpenCV ausente — capture_camera indisponível")
    report["problems"] = problems
    return report

register(ToolSpec("technical_diagnose", technical_diagnose, _v0, risk="low", mutating=False,
                  summary="Diagnóstico técnico agregado (diagnosticar primeiro, reparar depois)"))
