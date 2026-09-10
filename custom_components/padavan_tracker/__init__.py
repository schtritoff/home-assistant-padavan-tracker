"""The padavan-ng Tracker integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .router import PadavanRouter
from . import device_tracker, sensor  # noqa: F401 (preload platforms: avoids blocking import in event loop)

PLATFORMS = [Platform.DEVICE_TRACKER, Platform.SENSOR]


class PadavanConfigEntry(ConfigEntry["PadavanRouter"]):
    """Config entry for the padavan-ng Tracker integration."""

    runtime_data: PadavanRouter


async def async_setup_entry(hass: HomeAssistant, entry: PadavanConfigEntry) -> bool:
    """Set up padavan-ng platform."""

    router = PadavanRouter(hass, entry)

    async def async_update_listener(_hass: HomeAssistant) -> None:
        """Reload on options update."""
        await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await router.setup()

    async def async_close_connection(_event: Event) -> None:
        """Close padavan-ng connection on HA Stop."""
        await router.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    entry.runtime_data = router

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PadavanConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        router = entry.runtime_data
        await router.close()

    return unload_ok
