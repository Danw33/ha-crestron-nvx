"""Normalize presentation only, retaining custom labels and registry identity."""

from dataclasses import replace

import pytest
from crestron_nvx import NvxAvPort
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.binary_sensor import NvxAvPortBinarySensor
from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.entity import av_port_display_name
from custom_components.crestron_nvx.sensor import NvxAvPortSensor

from .conftest import DEVICE_ID, SNAPSHOT
from .test_entities import _coordinator


@pytest.mark.parametrize(
    "direction,name,port_id,expected",
    [
        ("input", "INPUT 1", "input_slot0_hdmi_0", "Input 1"),
        ("input", "input 2", "input_slot1_hdmi_0", "Input 2"),
        ("output", "OUTPUT 1", "output_slot0_hdmi_0", "Output 1"),
        ("output", "Output 1", "output_slot0_hdmi_0", "Output 1"),
        ("output", "output0", "output_slot0_port0", "Output 1"),
        ("input", "input1", "input_slot1_hdmi_0", "Input 2"),
        ("output", "output0", "output_index0_port0", "output0"),
        ("output", "output0", "output_slot1_port0", "output0"),
        ("output", "INPUT 1", "output_slot0_port0", "INPUT 1"),
        ("input", "output0", "input_slot0_port0", "output0"),
        ("input", "HDMI 1", "input_slot0_hdmi_0", "HDMI 1"),
        ("input", "Apple TV", "input_slot0_hdmi_0", "Apple TV"),
        ("input", "INPUT 1 - PC", "input_slot0_hdmi_0", "INPUT 1 - PC"),
        ("input", "INPUT 0", "input_slot0_hdmi_0", "INPUT 0"),
    ],
)
def test_port_labels(direction, name, port_id, expected):
    port = NvxAvPort(port_id=port_id, name=name, direction=direction)
    assert av_port_display_name(port) == expected
    assert port.name == name
    assert port.port_id == port_id


@pytest.mark.parametrize(
    "direction,name,expected,metrics",
    [
        ("input", "INPUT 1", "Input 1", ("sync",)),
        ("output", "output0", "Output 1", ("connected", "transmitting")),
    ],
)
def test_both_platforms_use_display_labels_without_changing_ids(
    direction, name, expected, metrics
):
    port = NvxAvPort(
        port_id=f"{direction}_slot0_hdmi_0", name=name, direction=direction
    )
    coordinator = _coordinator()
    sensor = NvxAvPortSensor(coordinator, port)
    assert sensor.translation_placeholders == {"port_name": expected}
    assert sensor.unique_id == f"{DEVICE_ID}_{direction}_{port.port_id}_resolution"
    for metric in metrics:
        binary = NvxAvPortBinarySensor(coordinator, port, metric)
        assert binary.translation_placeholders == {"port_name": expected}
        assert binary.unique_id == f"{DEVICE_ID}_{direction}_{port.port_id}_{metric}"


@pytest.mark.parametrize("custom_name", [None, "My TV connection"])
async def test_existing_registry_entry_survives_platform_setup(
    hass, mock_config_entry, mock_client, custom_name
):
    port = NvxAvPort(
        port_id="output_slot0_port0",
        name="output0",
        direction="output",
        sink_connected=False,
        transmitting=False,
    )
    mock_client.return_value = replace(SNAPSHOT, av_ports=(port,))
    registry = er.async_get(hass)
    unique_id = f"{DEVICE_ID}_output_{port.port_id}_connected"
    old = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        unique_id,
        config_entry=mock_config_entry,
        suggested_object_id="keep_my_existing_id",
        original_name="output0 output connected",
    )
    if custom_name:
        registry.async_update_entity(old.entity_id, name=custom_name)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    updated = registry.async_get(old.entity_id)
    assert updated.unique_id == unique_id
    assert updated.name == custom_name
    state = hass.states.get(old.entity_id)
    assert state is not None
    assert (custom_name or "Output 1 output connected") in state.attributes[
        "friendly_name"
    ]
    assert (
        registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
        == old.entity_id
    )
