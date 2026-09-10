"""padavan-ng status sensors."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import slugify

from .const import (
    KEY_COORDINATOR,
    KEY_SENSORS,
    SENSORS_CONNECTED_DEVICE,
)
from .router import PadavanRouter

if TYPE_CHECKING:
    from . import PadavanConfigEntry

UNIT_DEVICES = "Devices"


@dataclass(frozen=True)
class PadavanSensorEntityDescription(SensorEntityDescription):
    """A class that describes padavan-ng sensor entities."""

    factor: int | None = None


CONNECTION_SENSORS: tuple[PadavanSensorEntityDescription, ...] = (
    PadavanSensorEntityDescription(
        key=SENSORS_CONNECTED_DEVICE[0],
        translation_key="devices_connected",
        native_unit_of_measurement=UNIT_DEVICES,
    ),
    PadavanSensorEntityDescription(
        key="sensors_load_avg_1m",
        translation_key="load_avg_1m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_load_avg_5m",
        translation_key="load_avg_5m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_load_avg_15m",
        translation_key="load_avg_15m",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_percent",
        translation_key="memory_usage",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_used",
        translation_key="memory_used",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_free",
        translation_key="memory_free",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_total",
        translation_key="memory_total",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_cached",
        translation_key="memory_cached",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_mem_buffers",
        translation_key="memory_buffers",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_swap_used",
        translation_key="swap_used",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_swap_total",
        translation_key="swap_total",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
    ),
    PadavanSensorEntityDescription(
        key="sensors_uptime",
        translation_key="uptime",
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PadavanSensorEntityDescription(
        key="sensors_last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
    ),
)


def _convert_last_boot(value: float) -> datetime:
    """Convert a last boot epoch value to a UTC datetime."""
    return datetime.fromtimestamp(value, tz=timezone.utc)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: "PadavanConfigEntry",
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    router = entry.runtime_data
    entities = []

    for sensor_data in router.sensors_coordinator.values():
        coordinator = sensor_data[KEY_COORDINATOR]
        sensors = sensor_data[KEY_SENSORS]
        entities.extend(
            [
                PadavanSensor(coordinator, router, sensor_descr)
                for sensor_descr in CONNECTION_SENSORS
                if sensor_descr.key in sensors
            ]
        )

    async_add_entities(entities, True)


class PadavanSensor(CoordinatorEntity, SensorEntity):
    """Representation of a padavan-ng sensor."""

    entity_description: PadavanSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: PadavanRouter,
        description: PadavanSensorEntityDescription,
    ) -> None:
        """Initialize a padavan-ng sensor."""
        super().__init__(coordinator)
        self.entity_description = description

        self._router = router
        self._attr_unique_id = slugify(f"{router.unique_id}_{description.key}")
        self._attr_device_info = router.device_info

    @override
    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return current state."""
        descr = self.entity_description
        state: float | int | str | None = self.coordinator.data.get(descr.key)
        if state is None:
            return None
        if descr.key == "sensors_last_boot" and isinstance(state, (int, float)):
            return _convert_last_boot(float(state))
        if descr.key == "sensors_uptime" and isinstance(state, (int, float)):
            return int(state)
        return state
