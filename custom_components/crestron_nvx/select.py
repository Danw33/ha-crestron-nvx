"""Explicit configured A/V source selection, separate from active telemetry."""

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from crestron_nvx import NvxApiError, NvxAuthenticationError, NvxControlUnsupported

from .const import DOMAIN
from .coordinator import CrestronNvxConfigEntry, CrestronNvxCoordinator
from .entity import CrestronNvxEntity
from .routing import NvxReceiverStreamSelect

PARALLEL_UPDATES = 1

# HA option IDs must be valid translation keys; API values are case-sensitive.
VIDEO_SOURCE_TO_API = {
    "none": "None",
    "input_1": "Input1",
    "input_2": "Input2",
    "stream": "Stream",
}
AUDIO_SOURCE_TO_API = {
    "audio_follows_video": "AudioFollowsVideo",
    "input_1": "Input1",
    "input_2": "Input2",
    "analog_audio": "AnalogAudio",
    "primary_stream_audio": "PrimaryStreamAudio",
}
VIDEO_SOURCE_FROM_API = {value: key for key, value in VIDEO_SOURCE_TO_API.items()}
AUDIO_SOURCE_FROM_API = {value: key for key, value in AUDIO_SOURCE_TO_API.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CrestronNvxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register only for recognized sources on supported hardware."""
    entities: list[
        NvxVideoSourceSelect | NvxAudioSourceSelect | NvxReceiverStreamSelect
    ] = []
    if entry.runtime_data.data.primary_receive_stream is not None:
        entities.append(NvxReceiverStreamSelect(entry.runtime_data))
    if entry.runtime_data.data.video_source_options:
        entities.append(NvxVideoSourceSelect(entry.runtime_data))
    if entry.runtime_data.data.audio_source_options:
        entities.append(NvxAudioSourceSelect(entry.runtime_data))
    if entities:
        async_add_entities(entities)


class NvxVideoSourceSelect(CrestronNvxEntity, SelectEntity):
    """A disabled-by-default control; enabling it never writes."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "video_source"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "video_source_control")

    @property
    @override
    def options(self) -> list[str]:
        return [
            VIDEO_SOURCE_FROM_API[source]
            for source in self.coordinator.data.video_source_options
            if source in VIDEO_SOURCE_FROM_API
        ]

    @property
    @override
    def current_option(self) -> str | None:
        source = VIDEO_SOURCE_FROM_API.get(self.coordinator.data.video_source or "")
        return source if source in self.options else None

    @property
    @override
    def available(self) -> bool:
        return super().available and bool(self.options)

    @override
    async def async_select_option(self, option: str) -> None:
        if not self.available or option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="video_source_unavailable"
            )
        try:
            await self.coordinator.async_set_video_source(VIDEO_SOURCE_TO_API[option])
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="video_source_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="video_source_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="video_source_failed"
            ) from err


class NvxAudioSourceSelect(CrestronNvxEntity, SelectEntity):
    """Primary audio source with observed state and explicit actions only."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "audio_source"

    def __init__(self, coordinator: CrestronNvxCoordinator) -> None:
        super().__init__(coordinator, "audio_source_control")

    @property
    @override
    def options(self) -> list[str]:
        return [
            AUDIO_SOURCE_FROM_API[source]
            for source in self.coordinator.data.audio_source_options
            if source in AUDIO_SOURCE_FROM_API
        ]

    @property
    @override
    def current_option(self) -> str | None:
        source = AUDIO_SOURCE_FROM_API.get(self.coordinator.data.audio_source or "")
        return source if source in self.options else None

    @property
    @override
    def available(self) -> bool:
        return super().available and bool(self.options)

    @override
    async def async_select_option(self, option: str) -> None:
        if not self.available or option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="audio_source_unavailable"
            )
        try:
            await self.coordinator.async_set_audio_source(AUDIO_SOURCE_TO_API[option])
        except NvxControlUnsupported as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="audio_source_unsupported"
            ) from err
        except NvxAuthenticationError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="audio_source_auth_failed"
            ) from err
        except NvxApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="audio_source_failed"
            ) from err
