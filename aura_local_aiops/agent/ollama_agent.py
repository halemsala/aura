#!/usr/bin/env python3
"""
AURA Local Agent — usa Ollama para raciocinar e chama o Orchestrator local
quando precisa modificar o grafo Neo4j.
"""

from __future__ import annotations

import json
import os
import uuid
import urllib.request
from typing import Any

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
ORCH_URL = os.getenv("ORCH_URL", "http://127.0.0.1:8095/trigger")

SYSTEM_PROMPT = """Você é o AURA Agent local — um copiloto de operações autônomas.
Você tem acesso a uma ferramenta chamada trigger_neo4j que aplica queries Cypher
no banco de grafos Neo4j local.

Regras:
- Nunca invente dados. Se precisar alterar o grafo, use a ferramenta.
- Sempre forneça uma query de rollback quando fizer CREATE/MERGE/DELETE.
- Responda em português brasileiro, de forma técnica e direta.
- Se a pergunta for só de leitura/análise, não chame a ferramenta.
"""

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "trigger_neo4j",
        "description": "Aplica uma query Cypher no Neo4j local via Orchestrator (Harness local). Use para CREATE, MERGE, SET, DELETE etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "cypher_query": {
                    "type": "string",
                    "description": "Query Cypher a executar",
                },
                "rollback_cypher": {
                    "type": "string",
                    "description": "Query de rollback caso a principal falhe",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Se true, apenas simula sem aplicar",
                    "default": False,
                },
            },
            "required": ["cypher_query"],
        },
    },
}


def call_orchestrator(cypher_query: str, rollback_cypher: str = "", dry_run: bool = False) -> dict[str, Any]:
    corr = str(uuid.uuid4())
    payload = {
        "cypher_query": cypher_query,
        "rollback_cypher": rollback_cypher or "",
        "correlation_id": corr,
        "dry_run": dry_run,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ORCH_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat_ollama(messages: list[dict], tools: list | None = None) -> dict:
    body: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_agent(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # 1ª chamada — Ollama decide se usa a tool
    resp = chat_ollama(messages, tools=[TOOL_SPEC])
    msg = resp.get("message", {})
    tool_calls = msg.get("tool_calls") or []

    if not tool_calls:
        return msg.get("content") or "(sem resposta)"

    # Executa tools
    messages.append(msg)
    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name")
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        if name == "trigger_neo4j":
            print(f"[agent] chamando orchestrator: {args.get('cypher_query', '')[:80]}...")
            result = call_orchestrator(
                cypher_query=args.get("cypher_query", ""),
                rollback_cypher=args.get("rollback_cypher", ""),
                dry_run=bool(args.get("dry_run", False)),
            )
            messages.append({
                "role": "tool",
                "content": json.dumps(result, ensure_ascii=False),
            })
        else:
            messages.append({
                "role": "tool",
                "content": json.dumps({"error": f"tool desconhecida: {name}"}),
            })

    # 2ª chamada — Ollama formula a resposta final
    final = chat_ollama(messages)
    return final.get("message", {}).get("content") or "(sem resposta final)"


def main() -> None:
    print("=" * 50)
    print("  AURA Local Agent (Ollama + Neo4j)")
    print("=" * 50)
    print(f"  Modelo   : {OLLAMA_MODEL}")
    print(f"  Ollama   : {OLLAMA_HOST}")
    print(f"  Orch     : {ORCH_URL}")
    print("  Digite 'sair' para encerrar")
    print("=" * 50)

    while True:
        try:
            user = input("\nVocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrado.")
            break
        if not user:
            continue
        if user.lower() in ("sair", "exit", "quit"):
            break
        try:
            answer = run_agent(user)
            print(f"\nAURA> {answer}")
        except Exception as e:
            print(f"\n[erro] {e}")


if __name__ == "__main__":
    main()
