"""Checkpoints do Alfred. CLI: python -m alfred.checkpoint_cli create|list|restore-last|restore --zip X"""
import argparse, json, os, shutil, sys, time, zipfile
from pathlib import Path
from . import paths

INCLUDE = [paths.PROJECT_ROOT / "alfred", paths.PROJECT_ROOT / "config",
           paths.PROJECT_ROOT / "tests", paths.PROJECT_ROOT / "requirements-alfred.txt"]
EXCLUDE = {"__pycache__", ".git", "venv", ".venv", "node_modules"}


def create_checkpoint_zip() -> dict:
    ts = time.strftime("%Y%m%d-%H%M%S")
    zp = paths.CHECKPOINTS_DIR / f"ckpt-{ts}.zip"
    files = []
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for base in INCLUDE:
            if not base.exists():
                continue
            if base.is_file():
                arc = str(base.relative_to(paths.PROJECT_ROOT))
                z.write(base, arcname=arc)
                files.append(arc)
                continue
            for dp, dns, fns in os.walk(base):
                dns[:] = [d for d in dns if d not in EXCLUDE]
                for fn in fns:
                    fp = Path(dp) / fn
                    try:
                        if fp.stat().st_size > 5_000_000:
                            continue
                        arc = str(fp.relative_to(paths.PROJECT_ROOT))
                        z.write(fp, arcname=arc)
                        files.append(arc)
                    except OSError:
                        continue
        z.writestr("manifest.json", json.dumps({"created": ts, "files": files}))
    return {"checkpoint": str(zp), "files": len(files)}


def restore_zip(zip_path) -> dict:
    """Restaura por SOBREPOSIÇÃO: apenas ficheiros do manifest; nada fora é tocado.
    Antes do restauro, o estado actual é copiado para backups/pre-restore-*."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(str(zip_path))
    pre = paths.BACKUPS_DIR / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}"
    pre.mkdir(parents=True, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n != "manifest.json"]
        for n in names:
            src = paths.PROJECT_ROOT / n
            if src.exists():
                dst = pre / n
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        z.extractall(paths.PROJECT_ROOT)
        restored = len(names)
    return {"restored": restored, "from": str(zip_path), "pre_restore_backup": str(pre),
            "nota": "restauro por sobreposição, sem apagar nada fora do manifest"}


def restore_last() -> dict:
    zps = sorted(paths.CHECKPOINTS_DIR.glob("ckpt-*.zip"))
    if not zps:
        return {"restored": 0, "error": "não existem checkpoints — corre 'create' primeiro"}
    return restore_zip(zps[-1])


def list_checkpoints() -> list:
    out = []
    for zp in sorted(paths.CHECKPOINTS_DIR.glob("ckpt-*.zip")):
        try:
            with zipfile.ZipFile(zp) as z:
                man = json.loads(z.read("manifest.json"))
            out.append({"file": zp.name, "created": man.get("created"), "files": len(man.get("files", []))})
        except Exception:  # noqa: BLE001
            out.append({"file": zp.name, "created": "?", "files": "?"})
    return out


def main():
    ap = argparse.ArgumentParser(prog="alfred.checkpoint_cli")
    ap.add_argument("command", choices=["create", "list", "restore-last", "restore"])
    ap.add_argument("--zip", default=None)
    a = ap.parse_args()
    if a.command == "create":
        print(json.dumps(create_checkpoint_zip(), ensure_ascii=False, indent=2))
    elif a.command == "list":
        print(json.dumps(list_checkpoints(), ensure_ascii=False, indent=2))
    elif a.command == "restore-last":
        print(json.dumps(restore_last(), ensure_ascii=False, indent=2))
    else:
        if not a.zip:
            print("--zip é obrigatório para 'restore'")
            sys.exit(2)
        print(json.dumps(restore_zip(a.zip), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
