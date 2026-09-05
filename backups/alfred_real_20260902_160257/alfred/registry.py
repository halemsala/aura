from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ToolSpec:
    name: str
    fn: Callable
    validate: Callable
    risk: str                 # low | medium | high
    mutating: bool            # altera algo no computador?
    sensitive: bool = False   # exige execution_allowed=true ou token local
    summary: str = ""
    rollback: Optional[Callable] = None


TOOLS: dict = {}

def register(spec: ToolSpec) -> None:
    if spec.name in TOOLS:
        raise ValueError(f"ferramenta duplicada: {spec.name}")
    TOOLS[spec.name] = spec

def spec(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)

def capabilities() -> list:
    return [{"name": t.name, "risk": t.risk, "mutating": t.mutating,
             "sensitive": t.sensitive, "summary": t.summary}
            for t in sorted(TOOLS.values(), key=lambda x: x.name)]
