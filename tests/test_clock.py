"""Clock sync is opt-in and does not affect monitoring or stored settings."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxClockInfo,
    NvxConnectionError,
    NvxControlUnsupported,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.crestron_nvx.button import NvxClockSyncButton, async_setup_entry

from .conftest import DEVICE_ID
from .test_switch import coordinator


def ready(hass, entry):
    coord = coordinator(hass, entry)
    coord.clock_info = NvxClockInfo(True, True, True)
    coord.client.async_sync_clock = AsyncMock()
    entry.runtime_data = coord
    return coord, NvxClockSyncButton(coord)


async def test_setup_and_explicit_action(hass, mock_config_entry):
    coord, button = ready(hass, mock_config_entry)
    add = MagicMock()
    await async_setup_entry(hass, mock_config_entry, add)
    assert any(
        isinstance(entity, NvxClockSyncButton) for entity in add.call_args.args[0]
    )
    coord.client.async_sync_clock.assert_not_awaited()
    assert button.unique_id == f"{DEVICE_ID}_sync_clock_control"
    assert button.entity_category is EntityCategory.CONFIG
    assert not button.entity_registry_enabled_default
    await button.async_press()
    coord.client.async_sync_clock.assert_awaited_once_with(expected_device_id=DEVICE_ID)


@pytest.mark.parametrize(
    "info",
    [NvxClockInfo(), NvxClockInfo(True, False, True), NvxClockInfo(True, True, False)],
)
async def test_unavailable(hass, mock_config_entry, info):
    coord, button = ready(hass, mock_config_entry)
    coord.clock_info = info
    assert not button.available
    with pytest.raises(ServiceValidationError):
        await button.async_press()
    coord.client.async_sync_clock.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [NvxControlUnsupported, NvxConnectionError, NvxAuthenticationError]
)
async def test_command_error_preserves_monitoring(hass, mock_config_entry, error):
    coord, button = ready(hass, mock_config_entry)
    button.hass = hass
    coord.client.async_sync_clock.side_effect = error
    with patch.object(mock_config_entry, "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError):
            await button.async_press()
        assert reauth.call_count == int(error is NvxAuthenticationError)
    assert coord.last_update_success


async def test_optional_clock_failure_does_not_hide_monitoring(hass, mock_config_entry):
    coord, button = ready(hass, mock_config_entry)
    coord.client.async_get_clock_info.side_effect = NvxConnectionError
    await coord.async_refresh()
    assert coord.last_update_success and not button.available
    coord.client.async_sync_clock.assert_not_awaited()


async def test_cancel_releases_lock(hass, mock_config_entry):
    coord, button = ready(hass, mock_config_entry)
    coord.client.async_sync_clock.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await button.async_press()
    assert not coord._operation_lock.locked()


async def test_registry_opt_in_reload_and_no_implicit_write(
    hass, mock_config_entry, mock_client
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.crestron_nvx.const import DOMAIN

    with (
        patch(
            "crestron_nvx.NvxClient.async_get_clock_info",
            AsyncMock(return_value=NvxClockInfo(True, True, True)),
        ),
        patch("crestron_nvx.NvxClient.async_sync_clock", AsyncMock()) as command,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "button", DOMAIN, f"{DEVICE_ID}_sync_clock_control"
        )
        assert entity_id
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert (
            registry.async_get_entity_id(
                "button", DOMAIN, f"{DEVICE_ID}_sync_clock_control"
            )
            == entity_id
        )
        command.assert_not_awaited()
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
