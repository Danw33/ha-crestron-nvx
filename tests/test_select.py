"""Source controls use observed state and never write during lifecycle events."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxAvPort,
    NvxControlError,
    NvxControlUnsupported,
    NvxPermissionError,
    NvxPreviewInfo,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.select import (
    NvxVideoSourceSelect,
    async_setup_entry,
)

from .conftest import DEVICE_ID, SNAPSHOT
from .test_switch import coordinator

SOURCE = replace(
    SNAPSHOT,
    device_mode="Transmitter",
    video_source="None",
    auto_input_routing_enabled=False,
    av_ports=(NvxAvPort("input_slot0_hdmi_0", "INPUT 1", "input"),),
)


def source_coordinator(hass, entry):
    coord = coordinator(hass, entry)
    coord.async_set_updated_data(SOURCE)
    coord.client.async_set_video_source = AsyncMock(
        return_value=replace(SOURCE, video_source="Input1")
    )
    return coord


async def test_properties_and_verified_action(hass, mock_config_entry):
    coord = source_coordinator(hass, mock_config_entry)
    entity = NvxVideoSourceSelect(coord)
    assert entity.unique_id == f"{DEVICE_ID}_video_source_control"
    assert entity.entity_category is EntityCategory.CONFIG
    assert not entity.entity_registry_enabled_default
    assert entity.options == ["None", "Input1"]
    assert entity.current_option == "None"
    await entity.async_select_option("Input1")
    coord.client.async_set_video_source.assert_awaited_once_with(
        "Input1", expected_device_id=DEVICE_ID
    )
    assert entity.current_option == "Input1"


async def test_missing_and_invalid_options(hass, mock_config_entry):
    coord = source_coordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = coord
    entity = NvxVideoSourceSelect(coord)
    add = MagicMock()
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_called_once()
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option("Input2")
    coord.async_set_updated_data(replace(SOURCE, video_source=None))
    assert not entity.available
    assert entity.current_option is None
    add.reset_mock()
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_not_called()
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option("Input1")
    coord.client.async_set_video_source.assert_not_awaited()


@pytest.mark.parametrize(
    "error,expected",
    [
        (NvxControlUnsupported(), ServiceValidationError),
        (NvxPermissionError(), HomeAssistantError),
        (NvxControlError(), HomeAssistantError),
        (NvxAuthenticationError(), HomeAssistantError),
    ],
)
async def test_errors_preserve_monitoring(hass, mock_config_entry, error, expected):
    coord = source_coordinator(hass, mock_config_entry)
    coord.client.async_set_video_source.side_effect = error
    entity = NvxVideoSourceSelect(coord)
    entity.hass = hass
    with (
        patch.object(mock_config_entry, "async_start_reauth") as reauth,
        pytest.raises(expected),
    ):
        await entity.async_select_option("Input1")
    assert reauth.call_count == int(isinstance(error, NvxAuthenticationError))
    assert coord.last_update_success
    assert entity.current_option == "None"


async def test_registry_enable_service_reload_unload(
    hass, mock_config_entry, mock_client
):
    with (
        patch(
            "custom_components.crestron_nvx.NvxClient.async_get_snapshot",
            return_value=SOURCE,
        ),
        patch(
            "crestron_nvx.NvxClient.async_set_video_source",
            new_callable=AsyncMock,
            return_value=replace(SOURCE, video_source="Input1"),
        ) as write,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "select", DOMAIN, f"{DEVICE_ID}_video_source_control"
        )
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        write.assert_not_awaited()
        assert hass.states.get(entity_id).state == "None"
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "Input1"},
            blocking=True,
        )
        write.assert_awaited_once_with("Input1", expected_device_id=DEVICE_ID)
        assert hass.states.get(entity_id).state == "Input1"
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_poll_ordering_and_cancellation(hass, mock_config_entry):
    coord = source_coordinator(hass, mock_config_entry)
    entered, release = asyncio.Event(), asyncio.Event()

    async def preview():
        entered.set()
        await release.wait()
        return NvxPreviewInfo()

    coord.client.async_get_preview_info.side_effect = preview
    poll = asyncio.create_task(coord.async_refresh())
    await entered.wait()
    command = asyncio.create_task(coord.async_set_video_source("Input1"))
    await asyncio.sleep(0)
    coord.client.async_set_video_source.assert_not_awaited()
    release.set()
    await asyncio.gather(poll, command)
    assert coord.data.video_source == "Input1"
    coord.client.async_set_video_source.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await coord.async_set_video_source("None")
    assert not coord._operation_lock.locked()
