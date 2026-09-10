"""Client for Padavan-based routers (web interface access)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .const import LAN_CLIENTS_PATH, SYSINFO_PATH, SYSTEM_PAGE, FIRMWARE_PAGE

_LOGGER = logging.getLogger(__name__)

_IPMONITOR_RE = re.compile(
    r"var\s+ipmonitor(?:_last)?\s*=\s*(\[.*?\]);", re.DOTALL
)

# ipmonitor entry: [ip, mac, name, type, http, staled]
_IDX_IP = 0
_IDX_MAC = 1
_IDX_NAME = 2


@dataclass
class PadavanClient:
    """State of one client as seen by the router."""

    mac: str
    ip: str | None = None
    hostname: str | None = None
    staled: bool = False

    @classmethod
    def from_entry(cls, entry: list[Any]) -> PadavanClient | None:
        """Build a client from an ipmonitor row."""
        try:
            ip = entry[_IDX_IP]
            mac = entry[_IDX_MAC]
            name = entry[_IDX_NAME]
            staled = entry[5] == "1"
        except (IndexError, TypeError):
            return None
        if not isinstance(mac, str) or not mac:
            return None
        return cls(
            mac=normalize_mac(mac),
            ip=ip if isinstance(ip, str) else None,
            hostname=name if isinstance(name, str) and name and name != "*" else None,
            staled=staled,
        )


def normalize_mac(mac: str) -> str:
    """Normalize a MAC address to uppercase with colons."""
    mac = mac.strip().upper().replace("-", ":")
    if ":" not in mac and len(mac) == 12:
        mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))
    return mac


def format_mac(mac: str) -> str:
    """Normalize a MAC to the registry format (ha format_mac style)."""
    return normalize_mac(mac).lower()


_SYSINFO_RE = re.compile(r"var sysinfo = (?P<data>\{.*?\});", re.DOTALL)
_UPTIMESTR_RE = re.compile(r'var\s+uptimeStr\s*=\s*"([^"]+)"')
_LAVG_RE = re.compile(r'lavg:\s*"([^"]*)"')
_UPTIME_RE = re.compile(
    r"uptime:\s*\{days:\s*(\d+),\s*hours:\s*(\d+),\s*minutes:\s*(\d+)"
)
_RAM_RE = re.compile(
    r"ram:\s*\{total:\s*(\d+),\s*used:\s*(\d+),\s*free:\s*(\d+),"
    r"\s*buffers:\s*(\d+),\s*cached:\s*(\d+)"
)
_SWAP_RE = re.compile(r"swap:\s*\{total:\s*(\d+),\s*used:\s*(\d+),\s*free:\s*(\d+)")
_UPTIME_FORMAT = "%a, %d %b %Y %H:%M:%S %z"


def parse_sysinfo(text: str) -> dict[str, Any]:
    """Parse the sysinfo object from state.js into flat sensor values.

    Values mirror the asuswrt sensor keys: load avg, memory (MB), swap,
    uptime (s) and last boot timestamp (epoch seconds).
    """
    values: dict[str, Any] = {}
    match = _SYSINFO_RE.search(text)
    if not match:
        raise PadavanParseError("sysinfo object not found in state.js")
    data = match.group("data")

    if lavg_match := _LAVG_RE.search(data):
        loads = lavg_match.group(1).split()
        for i, key in enumerate(
            ("load_avg_1m", "load_avg_5m", "load_avg_15m")
        ):
            try:
                values[f"sensors_{key}"] = round(float(loads[i]), 2)
            except (IndexError, ValueError):
                values[f"sensors_{key}"] = None

    uptime_seconds = None
    if uptime_match := _UPTIME_RE.search(data):
        days, hours, minutes = (int(g) for g in uptime_match.groups())
        uptime_seconds = ((days * 24 + hours) * 60 + minutes) * 60
        values["sensors_uptime"] = uptime_seconds

    if uptimestr_match := _UPTIMESTR_RE.search(text):
        try:
            router_now = datetime.strptime(
                uptimestr_match.group(1), _UPTIME_FORMAT
            )
        except ValueError:
            router_now = None
        if router_now is not None and uptime_seconds is not None:
            last_boot = router_now - timedelta(seconds=uptime_seconds)
            values["sensors_last_boot"] = last_boot.timestamp()

    if ram_match := _RAM_RE.search(data):
        total, used, free, buffers, cached = (int(g) for g in ram_match.groups())
        # sysinfo.ram values are KB; expose MB rounded to 2 decimals.
        mb = 1024.0
        values["sensors_mem_total"] = round(total / mb, 2)
        values["sensors_mem_used"] = round(used / mb, 2)
        values["sensors_mem_free"] = round(free / mb, 2)
        values["sensors_mem_cached"] = round(cached / mb, 2)
        values["sensors_mem_buffers"] = round(buffers / mb, 2)
        if total:
            values["sensors_mem_percent"] = round(used / total * 100, 1)

    if swap_match := _SWAP_RE.search(data):
        swap_total, swap_used, _ = (int(g) for g in swap_match.groups())
        values["sensors_swap_total"] = round(swap_total / 1024.0, 2)
        values["sensors_swap_used"] = round(swap_used / 1024.0, 2)

    return values


class PadavanRouterError(Exception):
    """Base error for Padavan router communication."""


class PadavanConnectionError(PadavanRouterError):
    """Connection to the router failed."""


class PadavanAuthError(PadavanRouterError):
    """Authentication with the router failed."""


class PadavanParseError(PadavanRouterError):
    """Client list could not be parsed."""


class PadavanWebClient:
    """Talks to a padavan-ng router web interface."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.client.ClientSession,
        timeout: int = 10,
        verify_ssl: bool = False,
    ) -> None:
        """Initialize the router client."""
        self.host = normalize_host(host)
        self.username = username
        self.password = password
        self._session = session
        self._timeout = timeout
        # ssl=False disables certificate verification (padavan uses self-signed
        # certs); pass True to verify against the CA bundle.
        self._ssl = False if not verify_ssl else None

    async def async_get_connected_devices(self) -> dict[str, PadavanClient]:
        """Return fresh clients as mapping of formatted MAC to client."""
        text = await self._get_text(LAN_CLIENTS_PATH)
        clients = [
            client
            for client in parse_ipmonitor(text)
            if not client.staled
        ]
        return {format_mac(client.mac): client for client in clients}

    async def async_get_sysinfo(self) -> dict[str, Any]:
        """Return system info dict (load, memory, uptime) from state.js."""
        text = await self._get_text(SYSINFO_PATH)
        return parse_sysinfo(text)

    async def async_get_router_name(self) -> str | None:
        """Return the router host name as set in the web UI."""
        text = await self._get_text(SYSTEM_PAGE)
        match = re.search(r'name="computer_name2"[^>]*?value="([^"]*)"', text)
        if not match or not match.group(1):
            return None
        return match.group(1)

    async def async_get_firmware_version(self) -> str | None:
        """Return the firmware version from the firmware upgrade page."""
        text = await self._get_text(FIRMWARE_PAGE)
        match = re.search(
            r'name="firmver"[^>]*?value="([^"]*)"', text
        )
        if not match or not match.group(1):
            return None
        return match.group(1)

    def _auth(self) -> aiohttp.BasicAuth:
        """Return basic auth for the router."""
        return aiohttp.BasicAuth(self.username, self.password)

    async def _get_text(self, path: str) -> str:
        """GET a page and return its text."""
        url = f"{self.host}{path}"
        try:
            async with asyncio.timeout(self._timeout):
                resp = await self._session.get(url, auth=self._auth(), ssl=self._ssl)
        except TimeoutError as err:
            raise PadavanConnectionError(f"Timeout connecting to {url}") from err
        except OSError as err:
            raise PadavanConnectionError(f"Cannot connect to {url}: {err}") from err
        try:
            if resp.status == 401:
                raise PadavanAuthError(f"Authentication failed for {url}")
            if resp.status != 200:
                raise PadavanConnectionError(
                    f"Unexpected status {resp.status} from {url}"
                )
            text = await resp.text()
        except aiohttp.ClientError as err:
            raise PadavanParseError(f"Could not read response: {err}") from err
        finally:
            resp.release()
        return text


def normalize_host(host: str) -> str:
    """Normalize host into scheme://authority with no trailing slash."""
    host = host.strip()
    if not host:
        raise PadavanConnectionError("Host must not be empty")
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


def parse_ipmonitor(text: str) -> list[PadavanClient]:
    """Parse ipmonitor(_last) javascript array from a Padavan page."""
    match = _IPMONITOR_RE.search(text)
    if not match:
        raise PadavanParseError("ipmonitor array not found in response")
    try:
        entries = json.loads(match.group(1))
    except json.JSONDecodeError as err:
        raise PadavanParseError(f"ipmonitor array is not valid JSON: {err}") from err
    clients = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, list):
            continue
        client = PadavanClient.from_entry(entry)
        if client is None or client.mac in seen:
            continue
        seen.add(client.mac)
        clients.append(client)
    return clients
