"""Library capabilities drive HA controls without a second model allowlist."""

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.crestron_nvx import button, select, switch
from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.routing import primary_transmit_location

from .conftest import SNAPSHOT
from .test_routing import RX, TX, URL
from .test_switch import coordinator


@pytest.mark.parametrize(
    "model",
    [
        "DM-NVX-D30",
        "DM-NVX-351",
        "DM-NVX-352",
        "DM-NVX-363",
        "DM-NVX-FUTURE",
    ],
)
async def test_discovery_card_accepts_nvx_family(hass, model):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={"host": "192.0.2.45", "hostname": "synthetic-nvx", "model": model},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "connect"


@pytest.mark.parametrize(
    "model",
    [
        "DM-NVX-D30",
        "DM-NVX-351",
        "DM-NVX-352",
        "DM-NVX-363",
        "DM-NVX-FUTURE",
    ],
)
async def test_observed_receiver_controls_no_invented_inputs(
    hass, mock_config_entry, model
):
    coord = coordinator(hass, mock_config_entry)
    coord.async_set_updated_data(
        replace(
            RX,
            device=replace(RX.device, model=model),
            av_ports=(),
            receive_streams=(replace(RX.receive_streams[0], status="Stream started"),),
        )
    )
    mock_config_entry.runtime_data = coord
    add = MagicMock()
    await select.async_setup_entry(hass, mock_config_entry, add)
    entities = add.call_args.args[0]
    assert len(entities) == 3
    video = next(
        entity for entity in entities if isinstance(entity, select.NvxVideoSourceSelect)
    )
    assert video.options == ["none", "stream"]
    assert all(not entity.entity_registry_enabled_default for entity in entities)
    add.reset_mock()
    await button.async_setup_entry(hass, mock_config_entry, add)
    assert isinstance(add.call_args.args[0][0], button.NvxRebootButton)
    buttons = add.call_args.args[0]
    assert len(buttons) == 3
    assert {entity.translation_key for entity in buttons} == {
        "reboot",
        "receive_stream_start",
        "receive_stream_stop",
    }
    assert all(not entity.entity_registry_enabled_default for entity in buttons)
    add.reset_mock()
    await switch.async_setup_entry(hass, mock_config_entry, add)
    assert isinstance(add.call_args.args[0][0], switch.NvxLedSwitch)
    coord.client.async_set_leds_enabled.assert_not_awaited()


@pytest.mark.parametrize(
    "model", ["DM-NVX-351", "DM-NVX-352", "DM-NVX-363", "DM-NVX-FUTURE"]
)
def test_transmitter_catalogue_accepts_additional_models(model):
    source = replace(TX, device=replace(TX.device, model=model))
    assert primary_transmit_location(source) == URL
    assert primary_transmit_location(replace(source, device_mode="Receiver")) is None


async def test_capability_loss_marks_existing_controls_unavailable(
    hass, mock_config_entry
):
    coord = coordinator(hass, mock_config_entry)
    led = switch.NvxLedSwitch(coord)
    reboot = button.NvxRebootButton(coord)
    assert led.available and reboot.available
    coord.async_set_updated_data(
        replace(SNAPSHOT, device=replace(SNAPSHOT.device, model="CP4"))
    )
    assert not led.available and not reboot.available
    coord.async_set_updated_data(SNAPSHOT)
    assert led.available and reboot.available
