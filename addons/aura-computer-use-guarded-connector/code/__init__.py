"""AURA Computer Use Guarded Connector — inert by default."""
try:
    from .policy import GuardedPolicy, load_manifest
    from .connector import GuardedComputerUseConnector
except ImportError:
    from policy import GuardedPolicy, load_manifest  # type: ignore
    from connector import GuardedComputerUseConnector  # type: ignore

__version__ = "1.0.0"
__all__ = ["GuardedPolicy", "GuardedComputerUseConnector", "load_manifest"]
