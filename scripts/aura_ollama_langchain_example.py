"""Optional example: LangChain + Ollama (NOT required by AURA core).

Install only if you want experiments outside the Desktop:
  engine\\venv\\Scripts\\python.exe -m pip install langchain-ollama langchain-core

AURA production path remains: Engine -> HTTP REST -> Ollama :11434
"""
from __future__ import annotations

def main() -> None:
    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage
    except ImportError:
        print("Install: pip install langchain-ollama langchain-core")
        print("AURA itself does not need LangChain.")
        return

    llm = ChatOllama(model="llama3.2:3b", base_url="http://127.0.0.1:11434", temperature=0.2)
    # non-stream
    r = llm.invoke([HumanMessage(content="Diz apenas: OK LangChain")])
    print("invoke:", r.content)

    # stream
    print("stream:", end=" ")
    for chunk in llm.stream([HumanMessage(content="Conta ate 3")]):
        print(chunk.content or "", end="", flush=True)
    print()


if __name__ == "__main__":
    main()
