"""Tests for endpoint entities."""

from unittest.mock import MagicMock

from crestron_nvx import NvxPreviewInfo, NvxSnapshot

from custom_components.crestron_nvx.binary_sensor import (
    NvxDeviceReadyBinarySensor,
)
from custom_components.crestron_nvx.binary_sensor import (
    async_setup_entry as async_setup_binary_sensors,
)
from custom_components.crestron_nvx.image import async_setup_entry as async_setup_images
from custom_components.crestron_nvx.sensor import (
    SENSORS,
    NvxSensor,
)
from custom_components.crestron_nvx.sensor import (
    async_setup_entry as async_setup_sensors,
)

from .conftest import DEVICE_ID, SNAPSHOT


def _coordinator() -> MagicMock:
    """Return a coordinator-shaped object."""

    coordinator = MagicMock(data=SNAPSHOT, last_update_success=True)
    coordinator.preview_info = NvxPreviewInfo()
    coordinator.client.configuration_url = "https://nvx.example.local"
    return coordinator


def test_sensor_values_and_registry_data() -> None:
    """Expose values with stable IDs and one physical device."""

    coordinator = _coordinator()
    sensors = [NvxSensor(coordinator, description) for description in SENSORS]
    assert [sensor.native_value for sensor in sensors] == [
        "Receiver",
        "7.1.0",
        "Stream",
        "PrimaryStreamAudio",
        "Stream",
        "AudioFollowsVideo",
        "DAC",
        "PrimaryAudio",
        "PrimaryAudio",
        "poweron",
    ]
    assert sensors[0].unique_id == f"{DEVICE_ID}_device_mode"
    assert sensors[0].device_info["identifiers"] == {("crestron_nvx", DEVICE_ID)}


def test_ready_binary_sensor() -> None:
    """Expose endpoint readiness."""

    entity = NvxDeviceReadyBinarySensor(_coordinator())
    assert entity.is_on is True
    assert entity.unique_id == f"{DEVICE_ID}_device_ready"


async def test_platform_setup() -> None:
    """Add supported entities and leave the reserved image platform empty."""
    coordinator = _coordinator()
    entry = MagicMock(runtime_data=coordinator)
    add = MagicMock()
    await async_setup_sensors(MagicMock(), entry, add)
    sensor_entities = list(add.call_args.args[0])
    assert len(sensor_entities) == 18
    assert sensor_entities[10].native_value == "1920x1080@60"
    assert sensor_entities[12].native_value == "Started"
    assert sensor_entities[13].native_value == "1920x1080@60"
    assert sensor_entities[14].native_value == 800
    await async_setup_binary_sensors(MagicMock(), entry, add)
    binary_entities = list(add.call_args.args[0])
    assert len(binary_entities) == 11
    assert binary_entities[6].is_on is True
    assert binary_entities[7].is_on is True
    assert binary_entities[8].is_on is True
    assert binary_entities[9].is_on is True
    await async_setup_images(MagicMock(), entry, add)


async def test_platforms_skip_missing_values() -> None:
    """Avoid creating entities for fields absent on a model."""
    coordinator = _coordinator()
    coordinator.data = NvxSnapshot(device=SNAPSHOT.device)
    entry = MagicMock(runtime_data=coordinator)
    add = MagicMock()
    await async_setup_sensors(MagicMock(), entry, add)
    entities = list(add.call_args.args[0])
    assert [entity.entity_description.key for entity in entities] == [
        "firmware_version",
        "reboot_reason",
    ]
    add.reset_mock()
    await async_setup_binary_sensors(MagicMock(), entry, add)
    assert list(add.call_args.args[0]) == []
