"""Represent the padavan-ng router."""

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker import (
    CONF_CONSIDER_HOME,
    DEFAULT_CONSIDER_HOME,
    DOMAIN as TRACKER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import PadavanWebClient, PadavanRouterError
from .const import (
    CONF_REQUIRE_IP,
    CONF_TRACK_UNKNOWN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_REQUIRE_IP,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_UNKNOWN,
    KEY_COORDINATOR,
    KEY_METHOD,
    KEY_SENSORS,
    DOMAIN,
    REQUEST_TIMEOUT,
    SENSORS_CONNECTED_DEVICE,
    SENSORS_SYSINFO,
    SENSORS_TYPE,
    SENSORS_TYPE_COUNT,
)

if TYPE_CHECKING:
    from . import PadavanConfigEntry

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "padavan-ng Router"

CONF_REQ_RELOAD = [CONF_TRACK_UNKNOWN, CONF_REQUIRE_IP]


class PadavanSensorDataHandler:
    """Data handler for padavan-ng sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: PadavanWebClient,
        entry: "PadavanConfigEntry",
    ) -> None:
        """Initialize a padavan-ng sensor data handler."""
        self._hass = hass
        self._api = api
        self._entry = entry
        self._connected_devices = 0

    async def _get_connected_devices(self) -> dict[str, int]:
        """Return number of connected devices."""
        return {SENSORS_CONNECTED_DEVICE[0]: self._connected_devices}

    def update_device_count(self, conn_devices: int) -> bool:
        """Update connected devices attribute."""
        if self._connected_devices == conn_devices:
            return False
        self._connected_devices = conn_devices
        return True

    async def get_coordinator(
        self,
        sensor_type: str,
        update_method: Callable[[], Any] | None = None,
    ) -> DataUpdateCoordinator:
        """Get the coordinator for a specific sensor type."""
        should_poll = True
        if sensor_type == SENSORS_TYPE_COUNT:
            should_poll = False
            method = self._get_connected_devices
        elif update_method is not None:
            method = update_method
        else:
            raise RuntimeError(f"Invalid sensor type: {sensor_type}")

        coordinator = DataUpdateCoordinator(
            self._hass,
            _LOGGER,
            name=sensor_type,
            update_method=method,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=DEFAULT_SCAN_INTERVAL if should_poll else None,
            config_entry=self._entry,
        )
        await coordinator.async_refresh()

        return coordinator


def get_device_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return the device registry identifier of the router."""
    return (DOMAIN, entry.unique_id or "padavan_tracker")


class PadavanDevInfo:
    """Representation of a padavan-ng device info."""

    def __init__(self, mac: str, name: str | None = None) -> None:
        """Initialize a padavan-ng device info."""
        self._mac = mac
        self._name = name
        self._ip_address: str | None = None
        self._last_activity: datetime | None = None
        self._connected = False

    def update(
        self,
        ip_address: str | None = None,
        name: str | None = None,
        consider_home: int = 0,
    ) -> None:
        """Update padavan-ng device info."""
        utc_point_in_time = dt_util.utcnow()
        if ip_address is not None or (name and not self._name):
            if not self._name:
                self._name = name or self._mac.replace(":", "_")
            self._ip_address = ip_address
            self._last_activity = utc_point_in_time
            self._connected = True

        elif self._connected:
            self._connected = (
                self._last_activity is not None
                and (utc_point_in_time - self._last_activity).total_seconds()
                < consider_home
            )
            self._ip_address = None

    @property
    def is_connected(self) -> bool:
        """Return connected status."""
        return self._connected

    @property
    def mac(self) -> str:
        """Return device mac address."""
        return self._mac

    @property
    def name(self) -> str | None:
        """Return device name."""
        return self._name

    @property
    def ip_address(self) -> str | None:
        """Return device ip address."""
        return self._ip_address

    @property
    def last_activity(self) -> datetime | None:
        """Return device last activity."""
        return self._last_activity


class PadavanRouter:
    """Representation of a padavan-ng router."""

    def __init__(self, hass: HomeAssistant, entry: "PadavanConfigEntry") -> None:
        """Initialize a padavan-ng router."""
        self.hass = hass
        self._entry = entry

        self._devices: dict[str, PadavanDevInfo] = {}
        self._connected_devices: int = 0
        self._connect_error: bool = False

        self._router_name: str | None = None
        self._firmware_version: str | None = None

        self._sensors_data_handler: PadavanSensorDataHandler | None = None
        self._sensors_coordinator: dict[str, Any] = {}

        self._on_close: list[Callable] = []

        self._options: dict[str, str | bool | int] = {
            CONF_TRACK_UNKNOWN: DEFAULT_TRACK_UNKNOWN,
            CONF_REQUIRE_IP: DEFAULT_REQUIRE_IP,
        }
        self._options.update(entry.options)

        self._api: PadavanWebClient = PadavanWebClient(
            host=entry.data["host"],
            username=entry.data["username"],
            password=entry.data["password"],
            session=async_get_clientsession(hass),
            timeout=REQUEST_TIMEOUT,
            verify_ssl=entry.data.get("verify_ssl", False),
        )

    async def setup(self) -> None:
        """Set up a padavan-ng router."""
        try:
            await self._api.async_get_connected_devices()
        except (PadavanRouterError, OSError) as exc:
            raise ConfigEntryNotReady from exc

        # Router name and firmware (best effort; name falls back to host).
        try:
            self._router_name = await self._api.async_get_router_name()
            self._firmware_version = await self._api.async_get_firmware_version()
        except (PadavanRouterError, OSError) as err:
            _LOGGER.warning(
                "Could not fetch router name/firmware from %s: %s", self.host, err
            )

        # Register the router device (no sensor platform does it for us).
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self._entry.entry_id,
            identifiers={get_device_identifier(self._entry)},
            name=self.device_info["name"],
            model=self.device_info["model"],
            manufacturer=self.device_info["manufacturer"],
            sw_version=self.device_info.get("sw_version"),
            configuration_url=self._api.host,
        )

        # Load tracked entities from registry
        entity_reg = er.async_get(self.hass)
        track_entries = er.async_entries_for_config_entry(
            entity_reg, self._entry.entry_id
        )
        for entry in track_entries:
            if entry.domain != TRACKER_DOMAIN:
                continue
            device_mac = format_mac(entry.unique_id)

            # migrate entity unique ID if wrong formatted
            if device_mac != entry.unique_id:
                existing_entity_id = entity_reg.async_get_entity_id(
                    TRACKER_DOMAIN, DOMAIN, device_mac
                )
                if existing_entity_id:
                    # entity with uniqueid properly formatted already
                    # exists in the registry, we delete this duplicate
                    entity_reg.async_remove(entry.entity_id)
                    continue

                entity_reg.async_update_entity(
                    entry.entity_id, new_unique_id=device_mac
                )

            self._devices[device_mac] = PadavanDevInfo(device_mac, entry.original_name)

        # Update devices
        await self.update_devices()

        # Init Sensors
        await self.init_sensors_coordinator()

        self.async_on_close(
            async_track_time_interval(self.hass, self.update_all, self.update_interval)
        )

    async def update_all(self, now: datetime | None = None) -> None:
        """Update all padavan-ng platforms."""
        await self.update_devices()

    async def update_devices(self) -> None:
        """Update padavan-ng devices tracker."""
        new_device = False
        _LOGGER.debug("Checking devices for padavan router %s", self.host)
        try:
            wrt_devices = await self._api.async_get_connected_devices()
        except (OSError, PadavanRouterError) as exc:
            if not self._connect_error:
                self._connect_error = True
                _LOGGER.error(
                    "Error connecting to padavan router %s for device update: %s",
                    self.host,
                    exc,
                )
            return

        if self._connect_error:
            self._connect_error = False
            _LOGGER.warning("Reconnected to padavan router %s", self.host)

        self._connected_devices = len(wrt_devices)
        consider_home = int(
            self._options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME.total_seconds())
        )
        track_unknown = self._options.get(CONF_TRACK_UNKNOWN, DEFAULT_TRACK_UNKNOWN)
        require_ip = self._options.get(CONF_REQUIRE_IP, DEFAULT_REQUIRE_IP)

        for device_mac, device in self._devices.items():
            dev_info = wrt_devices.pop(device_mac, None)
            if dev_info is not None and require_ip and dev_info.ip is None:
                dev_info = None
            device.update(
                ip_address=dev_info.ip if dev_info else None,
                name=dev_info.hostname if dev_info else None,
                consider_home=consider_home,
            )

        for device_mac, dev_info in wrt_devices.items():
            if (
                not track_unknown
                and not dev_info.hostname
            ) or (require_ip and dev_info.ip is None):
                continue
            new_device = True
            device = PadavanDevInfo(device_mac)
            device.update(
                ip_address=dev_info.ip,
                name=dev_info.hostname,
                consider_home=consider_home,
            )
            self._devices[device_mac] = device
            # Per-client device registry entry, grouped under the router.
            dr.async_get(self.hass).async_get_or_create(
                config_entry_id=self._entry.entry_id,
                identifiers={(DOMAIN, f"client_{device_mac.replace(':', '')}")},
                connections={(CONNECTION_NETWORK_MAC, device_mac)},
                via_device=get_device_identifier(self._entry),
                name=device.name,
            )

        async_dispatcher_send(self.hass, self.signal_device_update)
        if new_device:
            async_dispatcher_send(self.hass, self.signal_device_new)
        await self._update_unpolled_sensors()

    async def init_sensors_coordinator(self) -> None:
        """Init padavan-ng sensors coordinators."""
        if self._sensors_data_handler:
            return

        self._sensors_data_handler = PadavanSensorDataHandler(
            self.hass, self._api, self._entry
        )
        self._sensors_data_handler.update_device_count(self._connected_devices)

        sensors_types: dict[str, dict[str, Any]] = {
            SENSORS_TYPE_COUNT: {KEY_SENSORS: SENSORS_CONNECTED_DEVICE},
            SENSORS_TYPE: {
                KEY_SENSORS: SENSORS_SYSINFO,
                KEY_METHOD: self._api.async_get_sysinfo,
            },
        }

        for sensor_type, sensor_def in sensors_types.items():
            if not (sensor_names := sensor_def.get(KEY_SENSORS)):
                continue
            coordinator = await self._sensors_data_handler.get_coordinator(
                sensor_type, update_method=sensor_def.get(KEY_METHOD)
            )
            self._sensors_coordinator[sensor_type] = {
                KEY_COORDINATOR: coordinator,
                KEY_SENSORS: sensor_names,
            }

    async def _update_unpolled_sensors(self) -> None:
        """Request refresh for padavan-ng unpolled sensors."""
        if not self._sensors_data_handler:
            return

        if SENSORS_TYPE_COUNT in self._sensors_coordinator:
            coordinator = self._sensors_coordinator[SENSORS_TYPE_COUNT][KEY_COORDINATOR]
            if self._sensors_data_handler.update_device_count(self._connected_devices):
                await coordinator.async_refresh()

    async def close(self) -> None:
        """Close the connection."""
        for func in self._on_close:
            func()
        self._on_close.clear()

    @callback
    def async_on_close(self, func: CALLBACK_TYPE) -> None:
        """Add a function to call when router is closed."""
        self._on_close.append(func)

    def update_options(self, new_options: Mapping[str, Any]) -> bool:
        """Update router options."""
        req_reload = False
        for name, new_opt in new_options.items():
            if name in CONF_REQ_RELOAD:
                old_opt = self._options.get(name)
                if old_opt is None or old_opt != new_opt:
                    req_reload = True
                    break

        self._options.update(new_options)
        return req_reload

    @property
    def entry(self) -> "PadavanConfigEntry":
        """Return the config entry."""
        return self._entry

    @callback
    def get_device_identifier(self) -> tuple[str, str]:
        """Return the device registry identifier of the router."""
        return get_device_identifier(self._entry)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        info = DeviceInfo(
            configuration_url=self._api.host,
            identifiers={get_device_identifier(self._entry)},
            name=self._router_name or f"padavan-ng Router ({self.host})",
            model=self._router_name or "padavan-ng router",
            manufacturer="Padavan-ng",
        )
        if self._firmware_version:
            info["sw_version"] = self._firmware_version
        return info

    @property
    def signal_device_new(self) -> str:
        """Event specific per padavan-ng entry to signal new device."""
        return f"{DOMAIN}-device-new"

    @property
    def signal_device_update(self) -> str:
        """Event specific per padavan-ng entry to signal updates in devices."""
        return f"{DOMAIN}-device-update"

    @property
    def host(self) -> str:
        """Return router hostname."""
        return self._api.host

    @property
    def update_interval(self) -> timedelta:
        """Return the scan interval."""
        return timedelta(
            seconds=self._options.get(
                CONF_UPDATE_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
            )
        )

    @property
    def sensors_coordinator(self) -> dict[str, Any]:
        """Return sensors coordinators."""
        return self._sensors_coordinator

    @property
    def unique_id(self) -> str:
        """Return router unique id."""
        return self._entry.unique_id or self._entry.entry_id

    @property
    def devices(self) -> dict[str, PadavanDevInfo]:
        """Return devices."""
        return self._devices
