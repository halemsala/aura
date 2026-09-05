"""AURA Maximizer: addon advisory, offline e inerte por padrão."""
from .agents import run_advisory, review_external_llm
from .connectors import ReadOnlyConnectorCatalog
from .contracts import EXECUTION_ALLOWED, GLM_ADVISORY_ONLY, PAPER_TRADE
from .firewall import parse_llm_output
from .routines import build_default_routines
from .orchestrator import AURAHermesPipeline, AURAProposal, Evidence, HermesReview, JointResult, Decision

__version__ = "1.0.0-safe-addon"


def status() -> dict[str, object]:
    return {
        "addon": "aura-maximizer",
        "version": __version__,
        "paper_trade": PAPER_TRADE,
        "execution_allowed": EXECUTION_ALLOWED,
        "glm_advisory_only": GLM_ADVISORY_ONLY,
        "network_enabled": False,
        "scheduler_enabled": False,
        "tool_execution_enabled": False,
    }


__all__ = [
    "EXECUTION_ALLOWED",
    "GLM_ADVISORY_ONLY",
    "PAPER_TRADE",
    "ReadOnlyConnectorCatalog",
    "build_default_routines",
    "parse_llm_output",
    "review_external_llm",
    "run_advisory",
    "status",
    "AURAHermesPipeline",
    "AURAProposal",
    "Evidence",
    "HermesReview",
    "JointResult",
    "Decision",
]
