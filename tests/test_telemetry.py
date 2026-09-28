"""Entity regressions for UUID churn, no signal and independent bitrate fields."""

from dataclasses import replace

from crestron_nvx.client import _parse_av_ports
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.binary_sensor import (
    NvxAvPortBinarySensor,
    NvxDeviceReadyBinarySensor,
    NvxStreamCodecReadyBinarySensor,
)
from custom_components.crestron_nvx.sensor import NvxAvPortSensor, NvxStreamSensor

from .conftest import SNAPSHOT
from .test_entities import _coordinator


def ports(sequence, signal):
    return _parse_av_ports(
        {
            "Device": {
                "AudioVideoInputOutput": {
                    "Inputs": [
                        {
                            "Name": "input0",
                            "Uuid": f"group-{sequence}",
                            "Ports": [
                                {
                                    "Uuid": f"port-{sequence}",
                                    "PortType": "Hdmi",
                                    "IsSyncDetected": signal,
                                    "Hdmi": {"Name": "INPUT 1"},
                                    "HorizontalResolution": 1920 if signal else 0,
                                    "VerticalResolution": 1080 if signal else 0,
                                    "FramesPerSecond": 60 if signal else 0,
                                }
                            ],
                        }
                    ]
                }
            }
        }
    )


def test_ports_remain_available_and_ids_survive_polling_and_reload():
    coordinator = _coordinator()
    coordinator.data = replace(SNAPSHOT, av_ports=ports(0, False))
    port = coordinator.data.av_ports[0]
    sync = NvxAvPortBinarySensor(coordinator, port, "sync")
    resolution = NvxAvPortSensor(coordinator, port)
    assert sync.available and sync.is_on is False
    assert resolution.available and resolution.native_value is None
    for sequence in range(1, 4):
        coordinator.data = replace(SNAPSHOT, av_ports=ports(sequence, True))
        assert sync.available and sync.is_on is True
        assert resolution.native_value == "1920x1080@60"
        reloaded = NvxAvPortSensor(coordinator, coordinator.data.av_ports[0])
        assert reloaded.unique_id == resolution.unique_id
    coordinator.data = replace(SNAPSHOT, av_ports=())
    assert not sync.available and sync.is_on is None
    assert not resolution.available and resolution.native_value is None


def test_active_bitrate_does_not_fall_back_or_disappear_when_missing():
    coordinator = _coordinator()
    stream = replace(
        SNAPSHOT.transmit_streams[0], bitrate_mbps=750, active_bitrate_mbps=686
    )
    coordinator.data = replace(SNAPSHOT, transmit_streams=(stream,))
    reported = NvxStreamSensor(coordinator, stream, 1, "bitrate")
    active = NvxStreamSensor(coordinator, stream, 1, "active_bitrate")
    assert reported.native_value == 750
    assert active.native_value == 686
    assert not reported.entity_registry_enabled_default
    assert active.entity_registry_enabled_default
    for value in (None, 0):
        coordinator.data = replace(
            SNAPSHOT, transmit_streams=(replace(stream, active_bitrate_mbps=value),)
        )
        assert active.available
        assert active.native_value == value
        assert reported.native_value == 750


def test_readiness_is_optional_diagnostic_without_inventing_health():
    coordinator = _coordinator()
    stream = replace(SNAPSHOT.transmit_streams[0], codec_ready=False)
    coordinator.data = replace(SNAPSHOT, device_ready=False, transmit_streams=(stream,))
    for entity in (
        NvxDeviceReadyBinarySensor(coordinator),
        NvxStreamCodecReadyBinarySensor(coordinator, stream, 1),
    ):
        assert entity.is_on is False
        assert entity.entity_category == EntityCategory.DIAGNOSTIC
        assert not entity.entity_registry_enabled_default


async def test_real_ha_registry_survives_polling_and_reload(
    hass, mock_config_entry, mock_client
):
    """Churning API UUIDs must not grow HA's registry or strand live entities."""
    mock_client.return_value = replace(SNAPSHOT, av_ports=ports(0, False))
    registry = er.async_get(hass)
    # An existing user's enabled readiness entity remains enabled after upgrade.
    ready = registry.async_get_or_create(
        "binary_sensor",
        "crestron_nvx",
        f"{SNAPSHOT.device.device_id}_device_ready",
        config_entry=mock_config_entry,
        disabled_by=None,
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entries = er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    identities = {(entity.entity_id, entity.unique_id) for entity in entries}
    sync_id = registry.async_get_entity_id(
        "binary_sensor",
        "crestron_nvx",
        f"{SNAPSHOT.device.device_id}_input_input_slot0_hdmi_0_sync",
    )
    assert hass.states.get(sync_id).state == "off"
    assert registry.async_get(ready.entity_id).disabled_by is None
    for sequence, signal in enumerate((True, False, True), start=1):
        mock_client.return_value = replace(SNAPSHOT, av_ports=ports(sequence, signal))
        await mock_config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(sync_id).state == ("on" if signal else "off")
    assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(sync_id).state == "on"
    assert identities == {
        (entity.entity_id, entity.unique_id)
        for entity in er.async_entries_for_config_entry(
            registry, mock_config_entry.entry_id
        )
    }
