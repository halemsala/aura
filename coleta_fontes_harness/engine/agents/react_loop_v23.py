# engine/agents/react_loop_v23.py — bounded ReAct, fail-closed, no real execution
from __future__ import annotations
from typing import Any, Callable


class ReActLoopV23:
    MAX_ITERATIONS = 5
    MAX_TOKENS_PER_ITERATION = 300
    EXECUTION_ALLOWED = False  # ABSOLUTE
    PAPER_TRADE = True

    def __init__(self, llm_client: Any, tool_registry: dict[str, Callable]):
        self.llm = llm_client
        self.tools = tool_registry or {}

    def execute(self, task: str) -> dict[str, Any]:
        history: list[dict[str, Any]] = []
        for i in range(self.MAX_ITERATIONS):
            prompt = self._build_react_prompt(task, history)
            try:
                raw_out = self.llm.generate(prompt, max_tokens=self.MAX_TOKENS_PER_ITERATION)
            except Exception as e:
                return {
                    "status": "llm_error",
                    "error": str(e)[:200],
                    "history": history,
                    "paper_trade": True,
                    "execution_allowed": False,
                }
            thought, action, action_input = self._parse_react(str(raw_out or ""))
            history.append({"thought": thought, "action": action, "input": action_input})
            if action == "FINAL_ANSWER":
                return {
                    "status": "success",
                    "result": action_input,
                    "iterations": i + 1,
                    "paper_trade": True,
                    "execution_allowed": False,
                }
            if action not in self.tools:
                history.append({"observation": f"ERROR: ferramenta '{action}' inexistente"})
                continue
            low = action.lower()
            if "execute" in low or "trade" in low or "order" in low:
                history.append({"observation": "BLOCKED: paper_trade=true, execution_allowed=false"})
                continue
            try:
                obs = self.tools[action](action_input)
                history.append({"observation": str(obs)[:2000]})
            except Exception as e:
                history.append({"observation": f"ERROR_FAILOVER: {e}"})
        return {
            "status": "max_iterations_reached",
            "history": history,
            "paper_trade": True,
            "execution_allowed": False,
        }

    def _build_react_prompt(self, task: str, history: list[dict]) -> str:
        hist_str = "\n".join(
            f"Thought: {h.get('thought')}\nAction: {h.get('action')}\nInput: {h.get('input')}\n"
            f"Observation: {h.get('observation', '')}"
            for h in history
        )
        return (
            f"Tools: {list(self.tools.keys())}\n"
            f"Task: {task}\n{hist_str}\n"
            "Respond EXACTLY:\nThought: <reasoning>\nAction: <tool_name>\nAction Input: <json_string>\n"
            "paper_trade=true. execution_allowed=false. Never execute real orders."
        )

    def _parse_react(self, text: str) -> tuple[str, str, str]:
        thought = text.split("Thought:")[1].split("Action:")[0].strip() if "Thought:" in text else ""
        action = (
            text.split("Action:")[1].split("Action Input:")[0].strip()
            if "Action:" in text
            else "ERROR_PARSE"
        )
        action_input = text.split("Action Input:")[1].strip() if "Action Input:" in text else "{}"
        return thought, action, action_input
