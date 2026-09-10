"""Support for padavan-ng routers as device tracker platform."""

from typing import TYPE_CHECKING, override

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    format_mac,
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .router import PadavanDevInfo, PadavanRouter

if TYPE_CHECKING:
    from . import PadavanConfigEntry

DEFAULT_DEVICE_NAME = "Unknown device"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PadavanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up device tracker for padavan-ng component."""
    router = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def update_router() -> None:
        """Update the values of the router."""
        add_entities(router, async_add_entities, tracked)

    router.async_on_close(
        async_dispatcher_connect(hass, router.signal_device_new, update_router)
    )

    update_router()


@callback
def add_entities(
    router: PadavanRouter,
    async_add_entities: AddConfigEntryEntitiesCallback,
    tracked: set[str],
) -> None:
    """Add new tracker entities from the router."""
    new_tracked = []

    for mac, device in router.devices.items():
        if mac in tracked:
            continue

        new_tracked.append(PadavanDevice(router, device))
        tracked.add(mac)

    async_add_entities(new_tracked)


class PadavanDevice(ScannerEntity):
    """Representation of a padavan-ng device."""

    _attr_should_poll = False

    def __init__(self, router: PadavanRouter, device: PadavanDevInfo) -> None:
        """Initialize a padavan-ng device."""
        self._router = router
        self._device = device
        self._attr_name = device.name or DEFAULT_DEVICE_NAME

    @property
    @override
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        return self._device.is_connected

    @property
    @override
    def hostname(self) -> str | None:
        """Return hostname of device."""
        return self._device.name

    @property
    @override
    def icon(self) -> str:
        """Return device icon."""
        return "mdi:lan-connect" if self._device.is_connected else "mdi:lan-disconnect"

    @property
    @override
    def ip_address(self) -> str | None:
        """Return the device ip address."""
        return self._device.ip_address

    @property
    @override
    def mac_address(self) -> str:
        """Return the device mac address."""
        return format_mac(self._device.mac)

    @callback
    def async_on_demand_update(self) -> None:
        """Update state."""
        if self._device.mac not in self._router.devices:
            return
        self._device = self._router.devices[self._device.mac]
        self.async_write_ha_state()

    @override
    async def async_internal_added_to_hass(self) -> None:
        """Handle added to Home Assistant."""
        await super().async_internal_added_to_hass()
        # Explicitly link this entity to its client device; ScannerEntity's
        # deferred MAC link only searches main devices and skips our child
        # devices (via_device).
        device_entry = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self._router.entry.entry_id,
            identifiers={
                (DOMAIN, f"client_{format_mac(self._device.mac).replace(':', '')}")
            },
            connections={(CONNECTION_NETWORK_MAC, self._device.mac)},
            via_device=self._router.get_device_identifier(),
        )
        if self.registry_entry and self.registry_entry.device_id != device_entry.id:
            er.async_get(self.hass).async_update_entity(
                self.entity_id, device_id=device_entry.id
            )

    @override
    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_device_update,
                self.async_on_demand_update,
            )
        )
