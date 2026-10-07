"""Small WebSocket load harness for a running local server.

Usage: python -m backend.tests.load_test --clients 100 --seconds 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

import websockets


async def participant(uri: str, duration: int, index: int) -> int:
    count = 0
    async with websockets.connect(uri, max_size=65536) as socket:
        await socket.recv()
        await socket.send(json.dumps({"type":"client_hello", "name":f"Load {index}", "institution":"Load test"}))
        deadline = time.monotonic() + duration
        sequence = 0
        while time.monotonic() < deadline:
            sequence += 1
            sent = time.time_ns() // 1_000_000
            await socket.send(json.dumps({"type":"ping", "sequence":sequence, "client_timestamp":sent}))
            pong = json.loads(await socket.recv())
            rtt = time.time_ns() // 1_000_000 - sent
            await socket.send(json.dumps({"type":"probe_result", "sequence":pong["sequence"], "sent_at":sent, "rtt_ms":rtt}))
            await socket.recv()
            count += 1
            await asyncio.sleep(1)
    return count


async def run(uri: str, clients: int, seconds: int) -> None:
    started = time.monotonic()
    results = await asyncio.gather(*(participant(uri, seconds, i) for i in range(clients)))
    print(f"clients={clients} probes={sum(results)} elapsed={time.monotonic()-started:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", default="ws://localhost:8080/ws")
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(run(args.uri, args.clients, args.seconds))
