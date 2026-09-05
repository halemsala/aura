"""AURA Maximizer: addon advisory, offline e inerte (v3.0 ToT + Ralph + Sandbox)."""
from .agents import run_advisory, review_external_llm
from .connectors import ReadOnlyConnectorCatalog
from .contracts import (
    EXECUTION_ALLOWED,
    GLM_ADVISORY_ONLY,
    PAPER_TRADE,
    AdvisoryDecision,
    DryRunAction,
    Severity,
)
from .firewall import parse_llm_output
from .routines import build_default_routines
from .orchestrator import (
    AURAHermesPipeline,
    AURAHermesPipelineV3,
    AURAProposal,
    Evidence,
    HermesReview,
    JointResult,
    Decision,
)
from .durable_state import (
    CheckpointStore,
    DurableGraph,
    GraphState,
    build_advisory_pipeline_graph,
)
from .sandbox import ContextEngine, VirtualSandbox
from .policies import PolicyEngine
from .observability import AuditLogger, make_event, redact
from .langchain_bridge import (
    AURARunnablePipeline,
    AURALangChainToolGuard,
    build_aura_langchain_chain,
    langchain_available,
)

__version__ = "3.0.0-safe-addon-tot-ralph"

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
        "features": [
            "ralph_loop",
            "tree_of_thoughts",
            "virtual_sandbox",
            "policy_engine",
            "audit_jsonl",
            "durable_state",
            "markdown_firewall",
            "langchain_bridge_optional",
        ],
    }

__all__ = [
    "EXECUTION_ALLOWED",
    "GLM_ADVISORY_ONLY",
    "PAPER_TRADE",
    "AdvisoryDecision",
    "DryRunAction",
    "Severity",
    "ReadOnlyConnectorCatalog",
    "build_default_routines",
    "parse_llm_output",
    "review_external_llm",
    "run_advisory",
    "status",
    "AURAHermesPipeline",
    "AURAHermesPipelineV3",
    "AURAProposal",
    "Evidence",
    "HermesReview",
    "JointResult",
    "Decision",
    "CheckpointStore",
    "DurableGraph",
    "GraphState",
    "build_advisory_pipeline_graph",
    "ContextEngine",
    "VirtualSandbox",
    "PolicyEngine",
    "AuditLogger",
    "make_event",
    "redact",
    "AURARunnablePipeline",
    "AURALangChainToolGuard",
    "build_aura_langchain_chain",
    "langchain_available",
]
