# engine/infra/background_workers.py
from __future__ import annotations
import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Optional

from engine.infra.dynamic_yield import YIELD
from engine.infra.priority_event_bus import BUS, PRIORITY_BACKGROUND

_EXECUTOR: Optional[ProcessPoolExecutor] = None

def get_executor(max_workers: int = 2) -> ProcessPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ProcessPoolExecutor(max_workers=max_workers)
    return _EXECUTOR

def _safe_call(fn_name: str) -> str:
    # runs in child process — import inside
    try:
        if fn_name == "director":
            from engine.aura_director_agent import AuraDirectorAgentV2
            AuraDirectorAgentV2().run_thinking_cycle()
            return "director_ok"
        if fn_name == "janitor":
            from engine.agents_glm.data_janitor_agent import classify_and_update
            classify_and_update()
            return "janitor_ok"
        if fn_name == "results":
            from engine.agents.results_agent import ResultsAgent
            return str(ResultsAgent().auto_label_day())
        if fn_name == "forensics":
            from engine.agents_glm.post_match_forensics import run_forensics
            return str(run_forensics("sample_match.jsonl"))
    except Exception as e:
        return f"err:{e}"
    return "noop"

async def background_worker(name: str, interval_live: float = 60.0, interval_idle: float = 15.0) -> None:
    loop = asyncio.get_event_loop()
    ex = get_executor()
    while True:
        YIELD.apply_nice()
        if YIELD.is_live and BUS.qsize() > 0:
            await asyncio.sleep(interval_live)
            continue
        try:
            await loop.run_in_executor(ex, _safe_call, name)
        except Exception:
            pass
        await asyncio.sleep(interval_live if YIELD.is_live else interval_idle)

async def start_all_background() -> None:
    asyncio.create_task(background_worker("director", 90.0, 30.0))
    asyncio.create_task(background_worker("janitor", 120.0, 45.0))
    asyncio.create_task(background_worker("results", 180.0, 60.0))
