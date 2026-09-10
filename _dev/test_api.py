"""Dev-only test: exercise the router client (devices, sysinfo, name, firmware)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
PKG = "padavan_tracker"
PKG_DIR = ROOT / "custom_components" / PKG

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(PKG_DIR)]
sys.modules[PKG] = pkg

client_spec = importlib.util.spec_from_file_location(
    f"{PKG}.client", PKG_DIR / "client.py"
)
client = importlib.util.module_from_spec(client_spec)
sys.modules[f"{PKG}.client"] = client
client_spec.loader.exec_module(client)

PadavanWebClient = client.PadavanWebClient
PadavanRouterError = client.PadavanRouterError
normalize_host = client.normalize_host


def load_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


async def main() -> None:
    """Fetch all frontend data surfaces."""
    env = load_env()
    async with __import__("aiohttp").ClientSession() as session:
        api = PadavanWebClient(
            host=normalize_host(env["host"]),
            username=env.get("user", "admin"),
            password=env["pass"],
            session=session,
        )
        try:
            devices = await api.async_get_connected_devices()
        except PadavanRouterError as err:
            print(f"FAIL devices: {err}")
            raise SystemExit(1)
        print(f"OK: {len(devices)} clients")
        try:
            sysinfo = await api.async_get_sysinfo()
        except PadavanRouterError as err:
            sysinfo = {}
            print(f"FAIL sysinfo: {err}")
        for key in sorted(sysinfo):
            print(f"  {key}: {sysinfo[key]}")
        name = await api.async_get_router_name()
        firmware = await api.async_get_firmware_version()
        print(f"router name: {name}")
        print(f"firmware: {firmware}")
        assert name and firmware, "router name or firmware missing"


if __name__ == "__main__":
    asyncio.run(main())
