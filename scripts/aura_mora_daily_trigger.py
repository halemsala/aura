#!/usr/bin/env python3
"""
aura_mora_daily_trigger.py — Disparo seguro do Agente MORA (agendamento diário).

Uso via cron:
  0 3 * * * /usr/bin/python3 /path/to/scripts/aura_mora_daily_trigger.py

Uso manual:
  python scripts/aura_mora_daily_trigger.py

Uso como daemon (espera até próximo 03:00):
  python scripts/aura_mora_daily_trigger.py --daemon
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Path setup
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MORA-TRIGGER] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Arquivo de lock para prevenir execução dupla
LOCK_FILE = ROOT / "data" / ".mora_running.lock"

# Timeout máximo do ciclo MORA (segundos) — previne travamento permanente
MORA_TIMEOUT_SEC = 1800  # 30 minutos


async def run_mora_once(project_root: Path) -> Path:
    """
    Executa um ciclo completo do MORA.
    Retorna caminho do relatório gerado.
    """
    # Imports tardios (só quando MORA roda, não no import do módulo)
    from engine.mora_resource_orchestrator import MoraResourceOrchestrator
    from engine.mora_daily_pipeline import MoraDailyPipeline
    from agents.glm_analysis_agent import GLMClient, GLMConfig

    # Carrega config do GLM
    config = GLMConfig()
    config_path = ROOT / "agents" / "glm_config.yaml"
    if config_path.exists():
        import yaml
        try:
            cfg_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if cfg_data:
                config.api_base = cfg_data.get("api_base", config.api_base)
                config.model_name = cfg_data.get("model_name", config.model_name)
        except Exception as e:
            logger.warning("Config GLM falhou, usando defaults: %s", e)

    glm_client = GLMClient(config)

    # Tenta carregar agent_registry e gpu_manager (opcionais — defensive)
    registry = None
    gpu_manager = None

    try:
        from engine.agent_registry import AgentRegistry
        registry = AgentRegistry()
        logger.info("AgentRegistry carregado")
    except ImportError:
        logger.warning("AgentRegistry nao disponivel — MORA rodara sem pausa de agentes")
    except Exception as e:
        logger.warning("Erro ao carregar AgentRegistry: %s", e)

    try:
        from engine.gpu_resource_manager import GpuResourceManager
        gpu_manager = GpuResourceManager()
        logger.info("GpuResourceManager carregado")
    except ImportError:
        logger.warning("GpuResourceManager nao disponivel — MORA sem alocacao de GPU")
    except Exception as e:
        logger.warning("Erro ao carregar GpuResourceManager: %s", e)

    # Cria orquestrador
    manifest_path = ROOT / "agents" / "activation_manifest.json"
    orchestrator = MoraResourceOrchestrator(
        agent_registry=registry,
        gpu_manager=gpu_manager,
        manifest_path=manifest_path,
    )

    # Cria pipeline
    output_dir = ROOT / "data" / "mora_reports"
    pipeline = MoraDailyPipeline(
        orchestrator=orchestrator,
        glm_client=glm_client,
        project_root=project_root,
        output_dir=output_dir,
    )

    # Executa com timeout
    logger.info("Iniciando ciclo MORA (timeout: %ds)...", MORA_TIMEOUT_SEC)
    try:
        report_path = await asyncio.wait_for(
            pipeline.run(), timeout=MORA_TIMEOUT_SEC
        )
        logger.info("Ciclo MORA concluido: %s", report_path)
        return report_path
    except asyncio.TimeoutError:
        logger.error("MORA TIMEOUT apos %ds — agentes devem ser verificados", MORA_TIMEOUT_SEC)
        raise
    except Exception as e:
        logger.error("MORA falhou: %s", e)
        raise


def acquire_lock() -> bool:
    """Tenta adquirir lock. Retorna True se conseguiu."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            content = LOCK_FILE.read_text(encoding="utf-8")
            data = json.loads(content)
            started = datetime.fromisoformat(data.get("started_at", ""))
            elapsed = datetime.now(timezone.utc) - started
            # Se passou do timeout, assume que travou e força
            if elapsed.total_seconds() > MORA_TIMEOUT_SEC:
                logger.warning("Lock obsoleto detectado (%ds), forçando", int(elapsed.total_seconds()))
                LOCK_FILE.unlink()
                return _write_lock()
            else:
                logger.warning("MORA ja rodando (iniciou %s ago)", int(elapsed.total_seconds()))
                return False
        except (json.JSONDecodeError, ValueError):
            # Lock corrompido — remove
            logger.warning("Lock corrompido, removendo")
            LOCK_FILE.unlink()
            return _write_lock()
    return _write_lock()


def _write_lock() -> bool:
    """Escreve arquivo de lock."""
    data = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    try:
        LOCK_FILE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Falha ao escrever lock: %s", e)
        return False


def release_lock() -> None:
    """Libera o lock."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except OSError:
        pass


async def run_daemon(target_hour: int = 3) -> None:
    """Modo daemon: espera até próximo target_hour e executa."""
    logger.info("MORA daemon ativo — executa diariamente as %02d:00", target_hour)
    while True:
        now = datetime.now()
        target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target = target + timedelta(days=1)
        wait_sec = (target - now).total_seconds()
        logger.info("Proxima execucao em %ds (%s)", int(wait_sec), target.isoformat())
        await asyncio.sleep(wait_sec)

        if not acquire_lock():
            continue
        try:
            await run_mora_once(ROOT)
        except Exception as e:
            logger.error("Ciclo falhou: %s", e)
        finally:
            release_lock()


def main():
    ap = argparse.ArgumentParser(description="MORA Daily Trigger")
    ap.add_argument("--daemon", action="store_true", help="Modo daemon")
    ap.add_argument("--hour", type=int, default=3, help="Hora de execucao (daemon)")
    ap.add_argument("--project-root", default=str(ROOT), type=Path)
    args = ap.parse_args()

    if args.daemon:
        asyncio.run(run_daemon(args.hour))
    else:
        # Execução única
        if not acquire_lock():
            logger.error("Abortando — MORA ja em execucao")
            sys.exit(1)
        try:
            asyncio.run(run_mora_once(args.project_root))
        except Exception as e:
            logger.error("MORA falhou: %s", e)
            sys.exit(1)
        finally:
            release_lock()


if __name__ == "__main__":
    main()