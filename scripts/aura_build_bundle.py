#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURA Build Bundle v1.0
Recompila o bundle React a partir do source atual e copia para matriz_v22.
Requer Node.js 18+ e pnpm instalados.
"""
import os, sys, shutil, subprocess, json
from pathlib import Path

AURA_ROOT = Path(os.environ.get("AURA_ROOT", os.getcwd()))
INTERFACE_DIR = AURA_ROOT / "interface" / "aura-quant-x-dashboard" / "client"
UI_TARGET = AURA_ROOT / "desktop" / "ui" / "matriz_v22"
BUILD_DIR = INTERFACE_DIR / "dist"

REQUIRED_COMPONENTS = [
    "AgentStudio", "TelegramControlCenter", "AtlasExportPanel",
    "ToolsActivationPanel", "GlobalDiagnosticPanel", "installAndActivateMax"
]


def log(msg: str):
    print(f"[BUILD] {msg}")


def check_prerequisites() -> bool:
    for cmd in ["node", "pnpm"]:
        if shutil.which(cmd) is None:
            log(f"ERRO: {cmd} nao encontrado no PATH. Instale Node.js 18+ e pnpm.")
            return False
    if not INTERFACE_DIR.exists():
        log(f"ERRO: Diretorio de interface nao encontrado: {INTERFACE_DIR}")
        return False
    return True


def install_deps() -> bool:
    log("Instalando dependencias com pnpm...")
    result = subprocess.run(["pnpm", "install"], cwd=INTERFACE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Falha no pnpm install: {result.stderr[:500]}")
        return False
    log("Dependencias instaladas.")
    return True


def build_project() -> bool:
    log("Executando pnpm build...")
    result = subprocess.run(["pnpm", "build"], cwd=INTERFACE_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Falha no build: {result.stderr[:1000]}")
        return False
    log("Build concluido com sucesso.")
    return True


def verify_bundle() -> dict:
    log("Verificando bundle gerado...")
    assets_dir = BUILD_DIR / "assets"
    if not assets_dir.exists():
        return {"ok": False, "error": "Pasta assets nao encontrada no dist"}
    js_files = list(assets_dir.glob("index-*.js"))
    css_files = list(assets_dir.glob("index-*.css"))
    if not js_files:
        return {"ok": False, "error": "Nenhum arquivo JS index-* encontrado"}
    if not css_files:
        return {"ok": False, "error": "Nenhum arquivo CSS index-* encontrado"}
    bundle_path = js_files[0]
    with open(bundle_path, "r", encoding="utf-8", errors="ignore") as f:
        bundle = f.read()
    missing = [c for c in REQUIRED_COMPONENTS if c not in bundle]
    if missing:
        return {"ok": False, "error": f"Componentes ausentes no bundle: {missing}"}
    return {
        "ok": True,
        "js_file": str(js_files[0].name),
        "css_file": str(css_files[0].name),
        "js_size": js_files[0].stat().st_size,
        "css_size": css_files[0].stat().st_size,
    }


def copy_to_matriz_v22(verify_result: dict) -> bool:
    log("Copiando assets para desktop/ui/matriz_v22/assets/...")
    target_assets = UI_TARGET / "assets"
    target_assets.mkdir(parents=True, exist_ok=True)
    for old in target_assets.glob("index-*"):
        old.unlink()
        log(f"  Removido: {old.name}")
    src_assets = BUILD_DIR / "assets"
    for f in src_assets.iterdir():
        if f.is_file():
            shutil.copy2(f, target_assets / f.name)
            log(f"  Copiado: {f.name} ({f.stat().st_size:,} bytes)")
    src_index = BUILD_DIR / "index.html"
    dst_index = UI_TARGET / "index.html"
    if src_index.exists():
        shutil.copy2(src_index, dst_index)
        log(f"  Copiado: index.html ({src_index.stat().st_size:,} bytes)")
    build_info = UI_TARGET / "BUILD_INFO.json"
    info = {
        "product": "AURA QUANT-X Operator OS — Original V25Q UI",
        "version": "12.7.62-V25Q-OPERATOR-OS-FINAL",
        "build_id": "12.7.62-V25Q-OPERATOR-OS-FINAL",
        "homepage": "index.html",
        "hosted_under": "/index.html",
        "notes": "Bundle recompilado com installAndActivateMax confirmado",
        "paper_trade": True,
        "execution_allowed": False,
        "bundle_js": verify_result["js_file"],
        "bundle_css": verify_result["css_file"],
        "js_size": verify_result["js_size"],
        "css_size": verify_result["css_size"],
    }
    with open(build_info, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    log("Copia concluida. Interface V25Q atualizada.")
    return True


def main():
    log("=" * 60)
    log("AURA Build Bundle v1.0")
    log(f"Interface: {INTERFACE_DIR}")
    log(f"Destino: {UI_TARGET}")
    log("=" * 60)
    if not check_prerequisites():
        return 1
    if not install_deps():
        return 1
    if not build_project():
        return 1
    verify = verify_bundle()
    if not verify["ok"]:
        log(f"ERRO na verificacao: {verify['error']}")
        return 1
    log(f"Bundle OK: JS={verify['js_file']} ({verify['js_size']:,} bytes), CSS={verify['css_file']} ({verify['css_size']:,} bytes)")
    if not copy_to_matriz_v22(verify):
        return 1
    log("=" * 60)
    log("BUILD CONCLUIDO COM SUCESSO")
    log("Reinicie o Desktop para aplicar as mudancas.")
    log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
