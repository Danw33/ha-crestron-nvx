"""Sensor entities for Crestron DM NVX."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import NvxAvPort, NvxSnapshot, NvxStream

from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NvxSensorDescription(SensorEntityDescription):
    """Describe a DM NVX sensor."""

    value_fn: Callable[[NvxSnapshot], Any]


SENSORS: tuple[NvxSensorDescription, ...] = (
    NvxSensorDescription(
        key="device_mode",
        translation_key="device_mode",
        value_fn=lambda data: data.device_mode,
    ),
    NvxSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.device.firmware_version,
    ),
    NvxSensorDescription(
        key="active_video_source",
        translation_key="active_video_source",
        value_fn=lambda data: data.active_video_source,
    ),
    NvxSensorDescription(
        key="active_audio_source",
        translation_key="active_audio_source",
        value_fn=lambda data: data.active_audio_source,
    ),
    NvxSensorDescription(
        key="video_source",
        translation_key="video_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.video_source,
    ),
    NvxSensorDescription(
        key="audio_source",
        translation_key="audio_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.audio_source,
    ),
    NvxSensorDescription(
        key="audio_mode",
        translation_key="audio_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.audio_mode,
    ),
    NvxSensorDescription(
        key="nax_active_audio_source",
        translation_key="nax_active_audio_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.nax_active_audio_source,
    ),
    NvxSensorDescription(
        key="nax_audio_source",
        translation_key="nax_audio_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.nax_audio_source,
    ),
    NvxSensorDescription(
        key="reboot_reason",
        translation_key="reboot_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.device.reboot_reason,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors for one endpoint."""

    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        NvxSensor(coordinator, description)
        for description in SENSORS
        if description.value_fn(coordinator.data) is not None
    ]
    entities.extend(
        NvxAvPortSensor(coordinator, port) for port in coordinator.data.av_ports
    )
    for streams in (
        coordinator.data.receive_streams,
        coordinator.data.transmit_streams,
    ):
        for index, stream in enumerate(streams, start=1):
            entities.extend(
                NvxStreamSensor(coordinator, stream, index, metric)
                for metric in ("status", "resolution", "bitrate")
            )
    async_add_entities(entities)


class NvxSensor(CrestronNvxEntity, SensorEntity):
    """Represent one read-only endpoint value."""

    entity_description: NvxSensorDescription

    def __init__(
        self, coordinator: CrestronNvxCoordinator, description: NvxSensorDescription
    ) -> None:
        """Initialize a sensor."""

        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def native_value(self) -> Any:
        """Return the current value."""

        return self.entity_description.value_fn(self.coordinator.data)


class NvxAvPortSensor(CrestronNvxEntity, SensorEntity):
    """Represent the detected resolution for one A/V port."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: CrestronNvxCoordinator, port: NvxAvPort) -> None:
        """Initialize an A/V port resolution sensor."""

        super().__init__(coordinator, f"{port.direction}_{port.port_id}_resolution")
        self._port_id = port.port_id
        self._direction = port.direction
        self._attr_translation_key = f"{port.direction}_resolution"
        self._attr_translation_placeholders = {"port_name": port.name}

    def _port(self) -> NvxAvPort | None:
        """Return the latest matching port."""

        return next(
            (
                port
                for port in self.coordinator.data.av_ports
                if port.port_id == self._port_id and port.direction == self._direction
            ),
            None,
        )

    @property
    @override
    def native_value(self) -> str | None:
        """Return the current detected resolution."""

        return port.resolution if (port := self._port()) else None

    @property
    @override
    def available(self) -> bool:
        """Mark a removed model-specific port unavailable."""

        return super().available and self._port() is not None


class NvxStreamSensor(CrestronNvxEntity, SensorEntity):
    """Represent one receive/transmit stream status value."""

    def __init__(
        self,
        coordinator: CrestronNvxCoordinator,
        stream: NvxStream,
        number: int,
        metric: str,
    ) -> None:
        """Initialize a stream sensor."""

        super().__init__(coordinator, f"{stream.direction}_{stream.stream_id}_{metric}")
        self._stream_id = stream.stream_id
        self._direction = stream.direction
        self._metric = metric
        self._attr_translation_key = f"{stream.direction}_stream_{metric}"
        self._attr_translation_placeholders = {"stream_number": str(number)}
        if metric == "bitrate":
            self._attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def _stream(self) -> NvxStream | None:
        """Return the latest matching stream."""

        streams = (
            self.coordinator.data.receive_streams
            if self._direction == "receive"
            else self.coordinator.data.transmit_streams
        )
        return next(
            (stream for stream in streams if stream.stream_id == self._stream_id),
            None,
        )

    @property
    @override
    def native_value(self) -> str | int | None:
        """Return the selected stream status value."""

        if (stream := self._stream()) is None:
            return None
        if self._metric == "status":
            return stream.status
        if self._metric == "resolution":
            return stream.resolution
        return stream.bitrate_mbps

    @property
    @override
    def available(self) -> bool:
        """Mark a removed stream slot unavailable."""

        return super().available and self._stream() is not None
