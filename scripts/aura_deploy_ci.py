#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Deploy CI v1.0
Pipeline de deploy automatizado: build, test, package e release.
"""
import os, sys, subprocess, shutil, json, zipfile
from pathlib import Path
from datetime import datetime

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
BUILD_DIR = AURA_ROOT / "build"
DIST_DIR = AURA_ROOT / "dist"


def run(cmd: list, cwd: Path = None, timeout: int = 300) -> dict:
    """Executa comando com log."""
    print(f"[DEPLOY] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or AURA_ROOT, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"[DEPLOY] ERRO: {result.stderr[:1000]}")
    return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}


def step_clean() -> bool:
    print("\n[STEP 1/6] Clean...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    BUILD_DIR.mkdir()
    DIST_DIR.mkdir()
    print("[DEPLOY] Diretórios limpos")
    return True


def step_build_react() -> bool:
    print("\n[STEP 2/6] Build React...")
    client = AURA_ROOT / "interface" / "aura-quant-x-dashboard" / "client"
    if not client.exists():
        print("[DEPLOY] AVISO: Interface React não encontrada, pulando")
        return True

    r = run(["pnpm", "install"], cwd=client)
    if not r["ok"]:
        return False

    r = run(["pnpm", "build"], cwd=client)
    if not r["ok"]:
        return False

    # Copiar para matriz_v22
    src = client / "dist"
    dst = AURA_ROOT / "desktop" / "ui" / "matriz_v22"
    if src.exists() and dst.exists():
        for f in (dst / "assets").glob("index-*"):
            f.unlink()
        for f in (src / "assets").iterdir():
            if f.is_file():
                shutil.copy2(f, dst / "assets" / f.name)
        shutil.copy2(src / "index.html", dst / "index.html")
        print("[DEPLOY] Bundle copiado para matriz_v22")

    return True


def step_tests() -> bool:
    print("\n[STEP 3/6] Tests...")
    smoke = AURA_ROOT / "scripts" / "smoke_test.py"
    if smoke.exists():
        r = run([sys.executable, str(smoke)])
        if not r["ok"]:
            print("[DEPLOY] Smoke test FALHOU")
            return False
        print("[DEPLOY] Smoke test PASSOU")
    else:
        print("[DEPLOY] AVISO: smoke_test.py não encontrado")

    # Pre-flight check
    preflight = AURA_ROOT / "scripts" / "aura_preflight_check.py"
    if preflight.exists():
        r = run([sys.executable, str(preflight)])
        if not r["ok"]:
            print("[DEPLOY] Pre-flight FALHOU")
            return False
        print("[DEPLOY] Pre-flight PASSOU")

    return True


def step_package() -> bool:
    print("\n[STEP 4/6] Package...")

    # Gerar BUILD_INFO
    build_info = AURA_ROOT / "desktop" / "ui" / "matriz_v22" / "BUILD_INFO.json"
    info = {
        "build_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "version": "12.7.62-V25Q-OPERATOR-OS-FINAL",
        "built_at": datetime.now().isoformat(),
        "git_commit": "N/A",
        "builder": "aura_deploy_ci",
    }
    build_info.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    # Criar ZIP de release
    version = info["version"]
    zip_name = f"AURA_QUANT_X_{version}_RELEASE.zip"
    zip_path = DIST_DIR / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(AURA_ROOT):
            # Ignorar diretórios desnecessários
            dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "dist", "build", "node_modules"]]
            for file in files:
                if file.endswith((".pyc", ".log", ".tmp")):
                    continue
                filepath = Path(root) / file
                arcname = filepath.relative_to(AURA_ROOT)
                zf.write(filepath, arcname)

    print(f"[DEPLOY] Pacote criado: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return True


def step_checksum() -> bool:
    print("\n[STEP 5/6] Checksum...")
    import hashlib

    for f in DIST_DIR.glob("*.zip"):
        sha256 = hashlib.sha256()
        with open(f, "rb") as fp:
            for chunk in iter(lambda: fp.read(8192), b""):
                sha256.update(chunk)
        hash_file = f.with_suffix(".sha256")
        hash_file.write_text(f"{sha256.hexdigest()}  {f.name}\n", encoding="utf-8")
        print(f"[DEPLOY] {f.name}: {sha256.hexdigest()}")

    return True


def step_manifest() -> bool:
    print("\n[STEP 6/6] Manifest...")
    manifest = {
        "product": "AURA QUANT-X Operator OS",
        "version": "12.7.62-V25Q-OPERATOR-OS-FINAL",
        "built_at": datetime.now().isoformat(),
        "artifacts": [f.name for f in DIST_DIR.iterdir()],
        "requirements": {
            "python": "3.10-3.11",
            "dotnet": "8.0 SDK (para compilar Desktop)",
            "node": "18+ (para build React)",
            "os": "Windows 10/11 x64",
            "gpu": "NVIDIA recomendada (fallback CPU disponível)",
        },
        "security": {
            "paper_trade": True,
            "execution_allowed": False,
            "glm_advisory_only": True,
        }
    }

    manifest_path = DIST_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[DEPLOY] Manifest: {manifest_path}")
    return True


def main():
    print("=" * 60)
    print("AURA Deploy CI v1.0")
    print("=" * 60)

    steps = [
        ("Clean", step_clean),
        ("Build React", step_build_react),
        ("Tests", step_tests),
        ("Package", step_package),
        ("Checksum", step_checksum),
        ("Manifest", step_manifest),
    ]

    results = []
    for name, step_func in steps:
        try:
            ok = step_func()
            results.append({"step": name, "ok": ok})
            if not ok:
                print(f"\n[DEPLOY] PIPELINE INTERROMPIDO em '{name}'")
                break
        except Exception as e:
            print(f"\n[DEPLOY] EXCEÇÃO em '{name}': {e}")
            results.append({"step": name, "ok": False, "error": str(e)})
            break

    passed = sum(1 for r in results if r["ok"])
    total = len(steps)

    print("\n" + "=" * 60)
    print(f"PIPELINE: {passed}/{total} steps concluídos")
    for r in results:
        status = "✅" if r["ok"] else "❌"
        print(f"  {status} {r['step']}")
    print(f"\nArtifacts em: {DIST_DIR}")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
