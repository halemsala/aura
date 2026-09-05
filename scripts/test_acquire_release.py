#!/usr/bin/env python3
"""
test_acquire_release.py — Teste isolado do ciclo acquire/release do MORA.
Verifica:
1. _acquire() pausa agentes (se registry disponível)
2. _release() retoma agentes
3. Manifest idêntico antes e depois
4. Invariantes preservados durante pausa
Defesa em camadas:
- Snapshot do manifest ANTES (memória + disco)
- Release com timeout próprio no finally
- Comparação manifest antes/depois no finally
- Restore de emergência se DIRTY
- Recusa correr se engine estiver ativo (porta 8765)
Uso:
  python scripts/test_acquire_release.py
"""
from __future__ import annotations
import asyncio
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MANIFEST_PATH = ROOT / "agents" / "activation_manifest.json"
SNAPSHOT_PATH = ROOT / "data" / ".test_manifest_snapshot.json"
ACQUIRE_TIMEOUT_SEC = 30
RELEASE_TIMEOUT_SEC = 10
# ============================================================================
# UTILITÁRIOS DE MANIFEST
# ============================================================================
def read_manifest() -> Dict[str, Any]:
    """Lê manifest do disco."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
def write_manifest(data: Dict[str, Any]) -> None:
    """Escreve manifest (UTF-8 sem BOM, indent=2)."""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
def snapshot_to_disk(data: Dict[str, Any]) -> None:
    """Persiste snapshot no disco para recovery de SIGKILL."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
def restore_from_memory(snapshot: Dict[str, Any]) -> None:
    """Restaura manifest do snapshot em memória."""
    write_manifest(snapshot)
    if SNAPSHOT_PATH.exists():
        SNAPSHOT_PATH.unlink()
def compare_manifests(
    before: Dict[str, Any], after: Dict[str, Any]
) -> List[str]:
    """Compara estado de agentes antes e depois. Retorna lista de diffs."""
    diffs: List[str] = []
    before_agents = before.get("agents", {})
    after_agents = after.get("agents", {})
    for name in before_agents:
        b = before_agents[name]
        a = after_agents.get(name)
        if a is None:
            diffs.append(f"{name}: AGENTE REMOVIDO do manifest")
            continue
        if b.get("status") != a.get("status"):
            diffs.append(
                f"{name}: status {b.get('status')} -> {a.get('status')}"
            )
        if b.get("paper_trade") != a.get("paper_trade"):
            diffs.append(
                f"{name}: paper_trade {b.get('paper_trade')} -> {a.get('paper_trade')}"
            )
        if b.get("execution_allowed") != a.get("execution_allowed"):
            diffs.append(
                f"{name}: execution_allowed "
                f"{b.get('execution_allowed')} -> {a.get('execution_allowed')}"
            )
    for name in after_agents:
        if name not in before_agents:
            diffs.append(f"{name}: AGENTE ADICIONADO ao manifest")
    return diffs
def check_engine_running() -> bool:
    """Verifica se o engine está activo (porta 8765)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        return sock.connect_ex(("127.0.0.1", 8765)) == 0
    finally:
        sock.close()
# ============================================================================
# TESTE PRINCIPAL
# ============================================================================
async def test_acquire_release_cycle() -> Dict[str, Any]:
    """
    Executa ciclo acquire/release isolado com timeout.
    Returns:
        Dict com: clean, error, paused_count, invariant_ok, diffs
    """
    result: Dict[str, Any] = {
        "clean": False,
        "error": None,
        "paused_count": 0,
        "invariant_ok": True,
        "diffs": [],
    }
    # === GUARD: não correr se engine está activo ===
    if check_engine_running():
        result["error"] = "engine_running — parar engine antes de testar"
        return result
    # === SNAPSHOT ANTES (memória + disco) ===
    try:
        before = read_manifest()
    except Exception as e:
        result["error"] = f"read_manifest_failed: {e}"
        return result
    snapshot_to_disk(before)
    agent_count = len(before.get("agents", {}))
    print(f"[1/5] Snapshot: {agent_count} agentes (cópia em {SNAPSHOT_PATH.name})")
    # === CARREGAR COMPONENTES (defensive) ===
    try:
        from engine.mora_resource_orchestrator import MoraResourceOrchestrator
    except ImportError as e:
        result["error"] = f"ImportError MoraResourceOrchestrator: {e}"
        restore_from_memory(before)
        return result
    registry = None
    try:
        from engine.agent_registry import AgentRegistry
        registry = AgentRegistry()
        has_set = hasattr(registry, "set_status")
        print(f"[2/5] AgentRegistry: {'OK (set_status existe)' if has_set else 'SEM set_status'}")
        if not has_set:
            result["error"] = "AgentRegistry sem set_status — acquire não vai pausar nada"
    except Exception as e:
        print(f"[2/5] AgentRegistry indisponível: {e}")
        result["error"] = f"registry_unavailable: {e}"
    gpu_manager = None
    try:
        from engine.gpu_resource_manager import GpuResourceManager
        gpu_manager = GpuResourceManager()
    except Exception:
        pass
    orchestrator = MoraResourceOrchestrator(
        agent_registry=registry,
        gpu_manager=gpu_manager,
        manifest_path=MANIFEST_PATH,
    )
    # === CICLO ACQUIRE / RELEASE ===
    lease = None
    try:
        print(f"[3/5] _acquire() — timeout {ACQUIRE_TIMEOUT_SEC}s...")
        lease = await asyncio.wait_for(
            orchestrator._acquire(),
            timeout=ACQUIRE_TIMEOUT_SEC,
        )
        # Verificar estado DURANTE pausa
        result["paused_count"] = sum(
            1 for a in lease.paused_agents if a.paused
        )
        result["invariant_ok"] = lease.is_valid
        if lease.invariant_violations:
            result["invariant_ok"] = False
            print(f" VIOLAÇÕES de invariantes: {lease.invariant_violations}")
        print(f" Agentes pausados: {result['paused_count']}")
        print(f" Invariantes: {'OK' if result['invariant_ok'] else 'VIOLADOS'}")
        if lease.vram_allocated_mb:
            print(f" VRAM alocada: {lease.vram_allocated_mb}MB")
    except asyncio.TimeoutError:
        result["error"] = f"acquire_timeout ({ACQUIRE_TIMEOUT_SEC}s)"
        print(f" TIMEOUT no acquire")
    except Exception as e:
        result["error"] = f"acquire_error: {e}"
        print(f" ERRO no acquire: {e}")
    finally:
        # === RELEASE (com timeout próprio) ===
        print(f"[4/5] _release() — timeout {RELEASE_TIMEOUT_SEC}s...")
        if lease is not None:
            try:
                await asyncio.wait_for(
                    orchestrator._release(lease),
                    timeout=RELEASE_TIMEOUT_SEC,
                )
                print(" Release: OK")
            except asyncio.TimeoutError:
                if result["error"] is None:
                    result["error"] = f"release_timeout ({RELEASE_TIMEOUT_SEC}s)"
                print(" TIMEOUT no release")
            except Exception as e:
                if result["error"] is None:
                    result["error"] = f"release_error: {e}"
                print(f" ERRO no release: {e}")
        # === VERIFICAÇÃO PÓS-CICLO ===
        print("[5/5] Verificação pós-ciclo...")
        try:
            after = read_manifest()
        except Exception as e:
            result["error"] = f"read_after_failed: {e}"
            print(f" ERRO ao ler manifest pós-ciclo: {e}")
            print(" RESTAURANDO do snapshot...")
            restore_from_memory(before)
            print(" Manifest restaurado")
            return result
        diffs = compare_manifests(before, after)
        result["diffs"] = diffs
        if diffs:
            print(f" DIRTY: {len(diffs)} diferenças")
            for d in diffs:
                print(f" {d}")
            print(" RESTAURANDO manifest do snapshot...")
            restore_from_memory(before)
            print(" Manifest restaurado")
        else:
            result["clean"] = True
            print(" CLEAN: manifest idêntico antes e depois")
        # Limpar snapshot do disco
        if SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.unlink()
    return result
# ============================================================================
# ENTRY POINT
# ============================================================================
def main() -> int:
    print("=" * 60)
    print("TESTE ISOLADO: MORA acquire / release cycle")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    print()
    result = asyncio.run(test_acquire_release_cycle())
    print()
    print("=" * 60)
    print("RESULTADO:")
    print(f" Clean: {result['clean']}")
    print(f" Error: {result['error']}")
    print(f" Pausados: {result['paused_count']}")
    print(f" Invariantes: {'OK' if result['invariant_ok'] else 'VIOLADOS'}")
    print(f" Diffs: {result['diffs']}")
    print("=" * 60)
    passed = (
        result["clean"]
        and result["invariant_ok"]
        and result["error"] is None
    )
    if passed:
        print("\n PASSOU — acquire/release é seguro para produção")
        return 0
    else:
        print("\n FALHOU — ver detalhes acima")
        if result["diffs"]:
            print(" NOTA: manifest foi restaurado do snapshot")
        if SNAPSHOT_PATH.exists():
            print(f" NOTA: snapshot em disco em {SNAPSHOT_PATH}")
            print(" remover manualmente se já restaurado")
        return 1
if __name__ == "__main__":
    sys.exit(main())
