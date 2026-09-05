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
    origin: str = "core"      # core | plugin


TOOLS: dict = {}
CORE_NAMES: set = set()


def register(spec: ToolSpec, replace: bool = False) -> None:
    if spec.name in TOOLS and not replace:
        raise ValueError(f"ferramenta duplicada: {spec.name}")
    if spec.name in CORE_NAMES and spec.origin == "plugin" and not replace:
        raise ValueError(f"não posso sobrepor ferramenta de núcleo: {spec.name}")
    TOOLS[spec.name] = spec


def unregister(name: str) -> bool:
    if name in CORE_NAMES:
        raise ValueError(f"ferramenta de núcleo não pode ser removida: {name}")
    return TOOLS.pop(name, None) is not None


def freeze_core() -> None:
    CORE_NAMES.update(TOOLS.keys())
    for t in TOOLS.values():
        t.origin = "core"


def is_core(name: str) -> bool:
    return name in CORE_NAMES


def spec(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def capabilities() -> list:
    return [{"name": t.name, "risk": t.risk, "mutating": t.mutating,
             "sensitive": t.sensitive, "summary": t.summary, "origin": t.origin}
            for t in sorted(TOOLS.values(), key=lambda x: x.name)]
