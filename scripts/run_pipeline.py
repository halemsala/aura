#!/usr/bin/env python3
"""
run_pipeline.py — Orquestra o pipeline B na ordem correta.

Uso:
  python scripts/run_pipeline.py            # ciclo completo
  python scripts/run_pipeline.py --watch    # daemon a cada 5min
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# Path do projeto
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agents.feedback_connector import FeedbackConnector
from agents.memory_store import MemoryStore
from agents.threshold_tuner import ThresholdTuner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PIPELINE] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


def run_cycle(regs_dir: Path, decisions_file: Path, config_path: Path,
              memory_path: Path, output_dir: Path) -> dict:
    """Executa um ciclo completo do pipeline B."""
    memory = MemoryStore(memory_path)

    # Passo 1: Feedback (resolve outcomes + calibra memória + relatório)
    logger.info("=== Passo 1: FeedbackConnector ===")
    conn = FeedbackConnector(
        regs_dir=regs_dir,
        decisions_file=decisions_file,
        memory=memory,
    )
    feedback_result = conn.run_cycle()
    logger.info(f"Feedback: {feedback_result['stats']}")

    # Passo 2: Tuning (propõe ajustes de threshold)
    logger.info("=== Passo 2: ThresholdTuner ===")
    tuner = ThresholdTuner(
        config_path=config_path,
        decisions_file=decisions_file,
        regs_dir=regs_dir,
        output_dir=output_dir,
    )
    tuning_result = tuner.run(lookback_days=7)
    logger.info(f"Tuning: {len(tuning_result['changes'])} mudanças propostas")
    logger.info(f"  Precision: {tuning_result['global_stats']['precision']:.1%}")
    logger.info(f"  Recall: {tuning_result['global_stats']['recall']:.1%}")

    # Passo 3: Prompt builder (validação de renderização)
    logger.info("=== Passo 3: PromptBuilder (validação) ===")
    from agents.prompt_builder import PromptContext, build_system_prompt
    import yaml
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    patterns = memory.best_patterns(min_n=3, min_rate=0.5)
    reliability = memory.trigger_reliability(["ap_rising"])
    ctx = PromptContext.from_config(cfg, validated_patterns=patterns,
                                    trigger_reliability=reliability)
    prompt = build_system_prompt(ctx)
    if "__" in prompt:
        logger.error("Placeholder não substituído no prompt!")
    else:
        logger.info("Prompt renderizado sem placeholders pendentes")

    return {
        "feedback": feedback_result,
        "tuning": tuning_result,
        "report": feedback_result["report_path"],
        "tomorrow_config": str(output_dir / "glm_config.tomorrow.yaml"),
    }


def main():
    ap = argparse.ArgumentParser(description="Pipeline B Orquestrador")
    ap.add_argument("--regs-dir", default="bridge/regs", type=Path)
    ap.add_argument("--decisions", default="data/glm_decisions.jsonl", type=Path)
    ap.add_argument("--config", default="agents/glm_config.yaml", type=Path)
    ap.add_argument("--memory", default="data/glm_memory.json", type=Path)
    ap.add_argument("--output", default="data/tuning", type=Path)
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()

    if args.watch:
        logger.info(f"Daemon ativo — ciclo a cada {args.interval}s")
        while True:
            try:
                run_cycle(args.regs_dir, args.decisions, args.config,
                         args.memory, args.output)
            except Exception as e:
                logger.error(f"Ciclo falhou: {e}")
            time.sleep(args.interval)
    else:
        result = run_cycle(args.regs_dir, args.decisions, args.config,
                          args.memory, args.output)
        print(f"\n✅ Pipeline concluído:")
        print(f"  Relatório: {result['report']}")
        print(f"  Config amanhã: {result['tomorrow_config']}")


if __name__ == "__main__":
    main()
