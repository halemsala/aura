#!/usr/bin/env python3
"""Skill personalizada — consome decisões do Multi-Agent Elite via WebSocket."""
import asyncio
import json

try:
    import websockets
except ImportError:
    raise SystemExit("pip install websockets")


async def main():
    uri = "ws://127.0.0.1:5000/api/skill/ws"
    print("Conectando skill:", uri)
    async with websockets.connect(uri) as ws:
        print("[Skill] Conectada ao Multi-Agent Elite Engine")
        while True:
            raw = await ws.recv()
            msg = json.loads(raw)
            if msg.get("event") != "MULTI_AGENT_DECISION":
                continue
            d = msg.get("data") or {}
            signal = d.get("signal")
            if signal in ("BUY_CORNER", "BUY_GOAL"):
                a = d.get("analytics") or {}
                print(
                    f"[SKILL DECISÃO] {d.get('match')} | {signal} | "
                    f"market={d.get('market')} | "
                    f"corner={a.get('cornerProbability')}% goal={a.get('goalProbability')}% | "
                    f"edgeC={a.get('cornerEdge')} kellyC={a.get('cornerStakeKelly')}"
                )


if __name__ == "__main__":
    asyncio.run(main())
