"""Dev-only: fetch recent HA error log entries via websocket system_log/list (uses .env)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiohttp


def load_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


async def main() -> None:
    """Fetch the HA error log buffer and print matching entries."""
    env = load_env()
    ws_url = env["ha_url"].replace("https://", "wss://").replace("http://", "ws://")
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"{ws_url}/api/websocket") as ws:
            await ws.receive()
            await ws.send_json({"type": "auth", "access_token": env["ha_token"]})
            await ws.receive()
            await ws.send_json({"id": 2, "type": "system_log/list"})
            while True:
                msg = json.loads((await ws.receive()).data)
                if msg.get("type") == "result":
                    break
            entries = msg.get("result", [])
            needle = sys.argv[1].lower() if len(sys.argv) > 1 else "padavan"
            print(f"[{len(entries)} entries in buffer]")
            for entry in entries:
                if needle in json.dumps(entry).lower():
                    print(entry.get("timestamp"), entry.get("level"), entry["name"])
                    print(" ", " ".join(entry["message"]) if isinstance(entry["message"], list) else entry["message"])
                    if entry.get("exception"):
                        print(entry["exception"])


if __name__ == "__main__":
    asyncio.run(main())
