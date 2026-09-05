# skill_client.py — Agente / Skill Personalizada (WebSocket)
import asyncio
import json

try:
    import websockets
except ImportError:
    raise SystemExit("pip install websockets")


async def conectar_skill():
    uri = "ws://127.0.0.1:5000/api/skill/ws"
    print("Conectando skill:", uri)
    async with websockets.connect(uri) as ws:
        print("[Skill Personalizada] Conectada ao Terminal Local GPU!")
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get("event") != "GPU_TELEMETRY_STREAM":
                continue
            payload = data.get("payload") or {}
            signal = payload.get("signal")
            analytics = payload.get("analytics") or {}
            if signal and signal != "HOLD":
                print(
                    f"[DECISÃO SKILL] {signal} | {payload.get('match')} | "
                    f"GPU corners={analytics.get('cornerProbabilityGPU')}% "
                    f"goals={analytics.get('goalProbabilityGPU')}%"
                )
                await ws.send(
                    json.dumps(
                        {
                            "action": "LOG_DECISION",
                            "status": "APPROVED",
                            "fixtureId": payload.get("fixtureId"),
                        }
                    )
                )


if __name__ == "__main__":
    asyncio.run(conectar_skill())
