"""LED controls preserve monitoring and require explicit service actions."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxControlError,
    NvxControlUnsupported,
    NvxPermissionError,
    NvxPreviewInfo,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.coordinator import CrestronNvxCoordinator
from custom_components.crestron_nvx.switch import NvxLedSwitch, async_setup_entry

from .conftest import DEVICE_ID, SNAPSHOT


def coordinator(hass, entry):
    client = MagicMock(
        async_get_snapshot=AsyncMock(return_value=SNAPSHOT),
        async_get_preview_info=AsyncMock(return_value=NvxPreviewInfo()),
        async_set_leds_enabled=AsyncMock(
            return_value=replace(SNAPSHOT, leds_enabled=False)
        ),
    )
    result = CrestronNvxCoordinator(hass, entry, client)
    result.async_set_updated_data(SNAPSHOT)
    return result


async def test_switch_properties_and_actions(hass, mock_config_entry):
    coord = coordinator(hass, mock_config_entry)
    switch = NvxLedSwitch(coord)
    assert switch.unique_id == f"{DEVICE_ID}_leds_control"
    assert switch.entity_category is EntityCategory.CONFIG
    assert switch.entity_registry_enabled_default is False
    assert switch.is_on is True
    await switch.async_turn_off()
    assert switch.is_on is False
    coord.client.async_set_leds_enabled.assert_awaited_once_with(
        False, expected_device_id=DEVICE_ID
    )
    coord.client.async_set_leds_enabled.return_value = SNAPSHOT
    await switch.async_turn_on()
    assert switch.is_on is True


async def test_missing_and_off_capability(hass, mock_config_entry):
    coord = coordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = coord
    coord.async_set_updated_data(replace(SNAPSHOT, leds_enabled=None))
    add = MagicMock()
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_not_called()
    switch = NvxLedSwitch(coord)
    assert switch.is_on is None
    assert not switch.available
    with pytest.raises(ServiceValidationError):
        await switch.async_turn_on()
    coord.client.async_set_leds_enabled.assert_not_awaited()
    coord.async_set_updated_data(replace(SNAPSHOT, leds_enabled=False))
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_called_once()


@pytest.mark.parametrize(
    "error,expected",
    [
        (NvxControlUnsupported(), ServiceValidationError),
        (NvxPermissionError(), HomeAssistantError),
        (NvxControlError(), HomeAssistantError),
    ],
)
async def test_failed_action_does_not_break_monitoring(
    hass, mock_config_entry, error, expected
):
    coord = coordinator(hass, mock_config_entry)
    coord.client.async_set_leds_enabled.side_effect = error
    switch = NvxLedSwitch(coord)
    with (
        patch.object(mock_config_entry, "async_start_reauth") as reauth,
        pytest.raises(expected),
    ):
        await switch.async_turn_off()
    reauth.assert_not_called()
    assert coord.last_update_success
    assert switch.is_on is True


async def test_confirmed_auth_failure_starts_reauth(hass, mock_config_entry):
    coord = coordinator(hass, mock_config_entry)
    coord.client.async_set_leds_enabled.side_effect = NvxAuthenticationError()
    switch = NvxLedSwitch(coord)
    switch.hass = hass
    with patch.object(mock_config_entry, "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError):
            await switch.async_turn_off()
        reauth.assert_called_once_with(hass)


async def test_registry_default_and_existing_binary_sensor(
    hass, mock_config_entry, mock_client
):
    with patch(
        "crestron_nvx.NvxClient.async_set_leds_enabled", new_callable=AsyncMock
    ) as write:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        switch_id = registry.async_get_entity_id(
            "switch", DOMAIN, f"{DEVICE_ID}_leds_control"
        )
        assert switch_id
        assert (
            registry.async_get(switch_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{DEVICE_ID}_leds_enabled"
        )
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        write.assert_not_awaited()
        assert (
            registry.async_get_entity_id("switch", DOMAIN, f"{DEVICE_ID}_leds_control")
            == switch_id
        )
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_poll_cannot_overwrite_later_command(hass, mock_config_entry):
    coord = coordinator(hass, mock_config_entry)
    entered, release = asyncio.Event(), asyncio.Event()

    async def preview():
        entered.set()
        await release.wait()
        return NvxPreviewInfo()

    coord.client.async_get_preview_info.side_effect = preview
    poll = asyncio.create_task(coord.async_refresh())
    await entered.wait()
    command = asyncio.create_task(coord.async_set_leds_enabled(False))
    await asyncio.sleep(0)
    coord.client.async_set_leds_enabled.assert_not_awaited()
    release.set()
    await asyncio.gather(poll, command)
    assert coord.data.leds_enabled is False


async def test_command_failure_releases_operation_lock(hass, mock_config_entry):
    coord = coordinator(hass, mock_config_entry)
    coord.client.async_set_leds_enabled.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await coord.async_set_leds_enabled(False)
    assert not coord._operation_lock.locked()
    await coord.async_refresh()
    assert coord.last_update_success


async def test_enabled_switch_service_and_unload(hass, mock_config_entry, mock_client):
    with patch(
        "crestron_nvx.NvxClient.async_set_leds_enabled",
        new_callable=AsyncMock,
        return_value=replace(SNAPSHOT, leds_enabled=False),
    ) as write:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "switch", DOMAIN, f"{DEVICE_ID}_leds_control"
        )
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        write.assert_not_awaited()
        assert hass.states.get(entity_id).state == "on"
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": entity_id}, blocking=True
        )
        write.assert_awaited_once_with(False, expected_device_id=DEVICE_ID)
        assert hass.states.get(entity_id).state == "off"
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
