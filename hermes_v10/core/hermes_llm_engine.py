#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes V10 Ultra â€” LLM Engine
Motor unificado de inferÃªncia com Ollama (local) + OpenAI (cloud fallback).
Suporta ReAct, tool-use, structured output e streaming.
"""
import os
import sys
import json
import re
import asyncio
import httpx
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
try:
    import structlog
except ImportError:
    import logging
    class _SL:
        @staticmethod
        def get_logger(name=None):
            return logging.getLogger(name or 'hermes')
    structlog = _SL()

logger = structlog.get_logger("hermes.llm_engine")


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    id: str = ""


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0


class ConstitutionGuard:
    """Bloqueia outputs que violam a constituiÃ§Ã£o do sistema."""

    DEFAULT_PATTERNS = [
        r"execution_allowed\s*=\s*true",
        r"allowRealOrders\s*:\s*true",
        r"aposta\s+real",
        r"live\s+trade",
        r"ordem\s+real",
        r"EXECUTION_ALLOWED\s*=\s*TRUE",
        r"paper_trade\s*=\s*false",
        r"PAPER_TRADE\s*=\s*FALSE",
    ]

    def __init__(self, extra_patterns: Optional[List[str]] = None):
        patterns = list(self.DEFAULT_PATTERNS)
        if extra_patterns:
            patterns.extend(extra_patterns)
        self.compiled = [re.compile(p, re.IGNORECASE) for p in patterns]

    def check(self, text: str) -> tuple[bool, Optional[str]]:
        for pat in self.compiled:
            if pat.search(text):
                return False, f"ConstituiÃ§Ã£o violada: padrÃ£o proibido detectado ({pat.pattern[:40]}...)"
        return True, None


class HermesLLMEngine:
    """
    Motor LLM com:
    - Ollama como primÃ¡rio (local, zero-custo)
    - OpenAI como fallback (cloud, alta capacidade)
    - ReAct loop integrado
    - Tool registry dinÃ¢mico
    - Constitution guard em toda saÃ­da
    """

    def __init__(
        self,
        ollama_host: str = "http://localhost:11434",
        ollama_model: str = "qwen3:8b",
        openai_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        constitution_patterns: Optional[List[str]] = None,
    ):
        self.ollama_host = ollama_host.rstrip("/")
        self.ollama_model = ollama_model
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self.openai_model = openai_model
        self.constitution = ConstitutionGuard(extra_patterns=constitution_patterns)
        self.tools: Dict[str, Callable] = {}
        self.http = httpx.AsyncClient(timeout=60.0)
        self._provider_priority = ["ollama"] + (["openai"] if bool(openai_key or os.getenv("OPENAI_API_KEY")) and os.getenv("HERMES_ALLOW_CLOUD") == "1" else [])  # fallback chain

    def register_tool(self, name: str, fn: Callable, description: str, params: Dict[str, Any]):
        """Registra uma ferramenta callable."""
        self.tools[name] = {
            "fn": fn,
            "description": description,
            "parameters": params,
        }
        logger.info("tool_registered", name=name)

    async def _call_ollama(
        self, messages: List[Dict], tools: Optional[List[Dict]] = None, stream: bool = False
    ) -> LLMResponse:
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": stream,
            "think": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "-1"),
            "options": {
                "temperature": float(os.getenv("AURA_OLLAMA_TEMPERATURE", "0.30")),
                "num_predict": int(os.getenv("AURA_OLLAMA_NUM_PREDICT", "1024")),
                "num_ctx": int(os.getenv("AURA_OLLAMA_NUM_CTX", "3072")),
                "num_gpu": int(os.getenv("OLLAMA_NUM_GPU", "99")),
            },
        }
        if tools:
            payload["tools"] = tools

        start = datetime.utcnow()
        try:
            r = await self.http.post(f"{self.ollama_host}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            delta = (datetime.utcnow() - start).total_seconds() * 1000

            content = data.get("message", {}).get("content", "")
            tool_calls = []
            for tc in data.get("message", {}).get("tool_calls", []):
                tool_calls.append(ToolCall(
                    name=tc.get("function", {}).get("name", ""),
                    arguments=tc.get("function", {}).get("arguments", {}),
                ))

            # Constitution check
            ok, reason = self.constitution.check(content)
            if not ok:
                logger.warning("constitution_block", reason=reason)
                content = f"[BLOQUEADO PELA CONSTITUIÃ‡ÃƒO] {reason}"

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                model=self.ollama_model,
                latency_ms=delta,
            )
        except Exception as e:
            logger.error("ollama_error", error=str(e))
            raise

    async def _call_openai(
        self, messages: List[Dict], tools: Optional[List[Dict]] = None, stream: bool = False
    ) -> LLMResponse:
        if not self.openai_key:
            raise RuntimeError("OPENAI_API_KEY nÃ£o configurada")

        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.openai_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        start = datetime.utcnow()
        r = await self.http.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        delta = (datetime.utcnow() - start).total_seconds() * 1000

        choice = data["choices"][0]
        content = choice["message"].get("content", "")
        tool_calls = []
        for tc in choice["message"].get("tool_calls", []):
            tool_calls.append(ToolCall(
                name=tc["function"]["name"],
                arguments=json.loads(tc["function"]["arguments"]),
                id=tc.get("id", ""),
            ))

        ok, reason = self.constitution.check(content)
        if not ok:
            logger.warning("constitution_block", reason=reason)
            content = f"[BLOQUEADO PELA CONSTITUIÃ‡ÃƒO] {reason}"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=self.openai_model,
            latency_ms=delta,
            tokens_used=data.get("usage", {}).get("total_tokens", 0),
        )

    async def chat(
        self,
        messages: List[Dict],
        use_tools: bool = True,
        max_tool_rounds: int = 5,
    ) -> LLMResponse:
        """
        Chat com ReAct loop automÃ¡tico de tool-use.
        Tenta Ollama primeiro, fallback para OpenAI.
        """
        tools_spec = []
        if use_tools and self.tools:
            for name, meta in self.tools.items():
                tools_spec.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": meta["description"],
                        "parameters": meta["parameters"],
                    }
                })

        last_error = None
        for provider in self._provider_priority:
            try:
                if provider == "ollama":
                    return await self._react_loop_ollama(messages, tools_spec, max_tool_rounds)
                else:
                    return await self._react_loop_openai(messages, tools_spec, max_tool_rounds)
            except Exception as e:
                last_error = e
                logger.warning(f"{provider}_failed", error=str(e))
                continue

        raise RuntimeError(f"Todos os providers falharam. Ãšltimo erro: {last_error}")

    async def _react_loop_ollama(self, messages, tools_spec, max_rounds):
        resp = None
        for _ in range(max_rounds):
            resp = await self._call_ollama(messages, tools=tools_spec)
            if not resp.tool_calls:
                return resp
            for tc in resp.tool_calls:
                result = await self._execute_tool(tc)
                messages.append({"role": "tool", "content": str(result), "name": tc.name})
        try:
            return await self._call_ollama(messages, tools=None)
        except Exception:
            return resp

    async def _react_loop_openai(self, messages, tools_spec, max_rounds):
        resp = None
        for _ in range(max_rounds):
            resp = await self._call_openai(messages, tools=tools_spec)
            if not resp.tool_calls:
                return resp
            for tc in resp.tool_calls:
                result = await self._execute_tool(tc)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": str(result),
                })
        try:
            return await self._call_openai(messages, tools=None)
        except Exception:
            return resp

    async def _execute_tool(self, tc: ToolCall) -> Any:
        if tc.name not in self.tools:
            return f"[ERRO] Ferramenta '{tc.name}' nÃ£o encontrada."
        try:
            fn = self.tools[tc.name]["fn"]
            if asyncio.iscoroutinefunction(fn):
                return await fn(**tc.arguments)
            return fn(**tc.arguments)
        except Exception as e:
            logger.error("tool_execution_error", tool=tc.name, error=str(e))
            return f"[ERRO] {type(e).__name__}: {e}"

    async def stream_chat(
        self, messages: List[Dict]
    ) -> AsyncGenerator[str, None]:
        """Streaming via Ollama (SSE-like)."""
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": True,
        }
        try:
            async with self.http.stream("POST", f"{self.ollama_host}/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error("stream_error", error=str(e))
            yield f"[ERRO DE STREAM] {e}"

    async def close(self):
        await self.http.aclose()


# â”€â”€â”€ Tool Implementations PadrÃ£o â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def tool_system_status() -> str:
    """Status AURA QUANT-X (portas locais). Nao e diagnostico do Windows."""
    import json as _json
    from urllib.request import Request, urlopen
    def ping(url):
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=2) as r:
                return r.status
        except Exception:
            return 0
    return _json.dumps({
        "produto": "AURA QUANT-X",
        "paper_trade": True,
        "execution_allowed": False,
        "bridge_8080": ping("http://127.0.0.1:8080/health"),
        "engine_8765": ping("http://127.0.0.1:8765/api/health"),
        "matriz_8766": ping("http://127.0.0.1:8766/health"),
        "hermes_8777": ping("http://127.0.0.1:8777/health"),
        "ollama_11434": ping("http://127.0.0.1:11434/api/tags"),
    }, ensure_ascii=False)


def tool_read_file(path: str, root: str = ".") -> str:
    """LÃª arquivo de texto com seguranÃ§a (path traversal bloqueado)."""
    from pathlib import Path
    if path and (path.startswith("/") or (len(path) >= 2 and path[1] == ":")):
        return "[ERRO] Path absoluto nao permitido."
    base = Path(root).resolve()
    target = (base / path).resolve()
    try:
        ok = target.is_relative_to(base)
    except AttributeError:
        ok = str(target).startswith(str(base) + ("\\" if str(base).endswith(":") else ("/" if "/" in str(base) else "\\"))) or target == base
    if not ok:
        return "[ERRO] Path traversal detectado."
    try:
        return target.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"[ERRO] {e}"


def tool_list_dir(path: str = ".", root: str = ".") -> str:
    """Lista diretÃ³rio com seguranÃ§a."""
    from pathlib import Path
    if path and (path.startswith("/") or (len(path) >= 2 and path[1] == ":")):
        return "[ERRO] Path absoluto nao permitido."
    base = Path(root).resolve()
    target = (base / path).resolve()
    try:
        ok = target.is_relative_to(base)
    except AttributeError:
        ok = str(target).startswith(str(base) + ("\\" if str(base).endswith(":") else ("/" if "/" in str(base) else "\\"))) or target == base
    if not ok:
        return "[ERRO] Path traversal detectado."
    try:
        items = []
        for p in target.iterdir():
            items.append({"name": p.name, "type": "dir" if p.is_dir() else "file", "size": p.stat().st_size})
        return json.dumps(items, ensure_ascii=False)
    except Exception as e:
        return f"[ERRO] {e}"


def tool_search_logs(keyword: str, root: str = ".", max_lines: int = 50) -> str:
    """Busca keyword em logs_supervisor/*.log e logs_supervisor/*.txt"""
    from pathlib import Path
    import glob
    base = Path(root) / "logs_supervisor"
    results = []
    for log_file in glob.glob(str(base / "*.log")) + glob.glob(str(base / "*.txt")):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                try:
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 200_000))
                    if size > 200_000:
                        f.readline()
                except Exception:
                    f.seek(0)
                for i, line in enumerate(f):
                    if keyword.lower() in line.lower():
                        results.append({"file": Path(log_file).name, "line": i+1, "text": line.strip()})
                        if len(results) >= max_lines:
                            break
        except Exception:
            continue
    return json.dumps(results[:max_lines], ensure_ascii=False)


def tool_check_constitution(text: str) -> str:
    """Verifica se texto viola constituiÃ§Ã£o."""
    g = ConstitutionGuard()
    ok, reason = g.check(text)
    return json.dumps({"safe": ok, "reason": reason}, ensure_ascii=False)


async def main():
    """CLI entrypoint para teste do motor."""
    engine = HermesLLMEngine()
    engine.register_tool("system_status", tool_system_status, "Retorna status do sistema", {"type": "object", "properties": {}})
    engine.register_tool("read_file", tool_read_file, "LÃª arquivo de texto", {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo do arquivo"},
            "root": {"type": "string", "description": "DiretÃ³rio raiz"},
        },
        "required": ["path"],
    })
    engine.register_tool("list_dir", tool_list_dir, "Lista diretÃ³rio", {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo"},
            "root": {"type": "string"},
        },
    })
    engine.register_tool("search_logs", tool_search_logs, "Busca em logs", {
        "type": "object",
        "properties": {
            "keyword": {"type": "string"},
            "root": {"type": "string"},
            "max_lines": {"type": "integer", "default": 50},
        },
        "required": ["keyword"],
    })
    engine.register_tool("check_constitution", tool_check_constitution, "Verifica constituiÃ§Ã£o", {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    })

    messages = [
        {"role": "system", "content": "VocÃª Ã© o Hermes V10 Ultra. Use ferramentas quando necessÃ¡rio. Responda em portuguÃªs."},
        {"role": "user", "content": "Qual o status do sistema e liste os arquivos na raiz?"},
    ]
    resp = await engine.chat(messages)
    print(json.dumps({
        "content": resp.content,
        "model": resp.model,
        "latency_ms": resp.latency_ms,
    }, ensure_ascii=False, indent=2))
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())

