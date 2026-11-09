"""Configured display commands are opt-in, stable and explicit."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxConnectionError,
    NvxControlUnsupported,
    NvxDisplayCommand,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.button import (
    NvxDisplayCommandButton,
    async_setup_entry,
)
from custom_components.crestron_nvx.const import DOMAIN

from .conftest import DEVICE_ID
from .test_switch import coordinator

COMMAND = NvxDisplayCommand("Output1", "PowerOn", "Cec", "Port1")


def ready(hass, entry):
    coord = coordinator(hass, entry)
    coord.display_commands = (COMMAND,)
    coord.client.async_send_display_command = AsyncMock()
    entry.runtime_data = coord
    return coord, NvxDisplayCommandButton(coord, COMMAND)


async def test_setup_and_press(hass, mock_config_entry):
    coord, entity = ready(hass, mock_config_entry)
    add = MagicMock()
    await async_setup_entry(hass, mock_config_entry, add)
    assert (
        sum(isinstance(item, NvxDisplayCommandButton) for item in add.call_args.args[0])
        == 1
    )
    coord.client.async_send_display_command.assert_not_awaited()
    assert entity.unique_id == f"{DEVICE_ID}_output1_display_power_on"
    assert not entity.entity_registry_enabled_default
    assert entity.entity_category is None
    await entity.async_press()
    coord.client.async_send_display_command.assert_awaited_once_with(
        "Output1", "PowerOn", expected_device_id=DEVICE_ID
    )


async def test_removed_command_and_optional_failure(hass, mock_config_entry):
    coord, entity = ready(hass, mock_config_entry)
    coord.client.async_get_display_commands.side_effect = NvxConnectionError
    await coord.async_refresh()
    assert coord.last_update_success and not entity.available
    with pytest.raises(ServiceValidationError):
        await entity.async_press()
    coord.client.async_send_display_command.assert_not_awaited()


async def test_current_mapping_preserves_output_identity(hass, mock_config_entry):
    coord, entity = ready(hass, mock_config_entry)
    coord.display_commands = (replace(COMMAND, interface="Serial", port_id="Port2"),)
    assert entity.available
    assert (
        NvxDisplayCommandButton(coord, coord.display_commands[0]).unique_id
        == entity.unique_id
    )
    coord.display_commands = (replace(COMMAND, output_id="Output2"),)
    assert not entity.available


@pytest.mark.parametrize(
    "error", [NvxControlUnsupported, NvxConnectionError, NvxAuthenticationError]
)
async def test_errors_preserve_monitoring(hass, mock_config_entry, error):
    coord, entity = ready(hass, mock_config_entry)
    entity.hass = hass
    coord.client.async_send_display_command.side_effect = error
    with patch.object(mock_config_entry, "async_start_reauth") as reauth:
        with pytest.raises(HomeAssistantError):
            await entity.async_press()
        assert reauth.call_count == int(error is NvxAuthenticationError)
    assert coord.last_update_success


async def test_cancel_unlocks(hass, mock_config_entry):
    coord, entity = ready(hass, mock_config_entry)
    coord.client.async_send_display_command.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await entity.async_press()
    assert not coord._operation_lock.locked()


async def test_registry_names_opt_in_and_no_implicit_commands(
    hass, mock_config_entry, mock_client
):
    commands = tuple(
        replace(COMMAND, action=action)
        for action in ("PowerOn", "PowerOff", "InputControl")
    )
    with (
        patch(
            "crestron_nvx.NvxClient.async_get_display_commands",
            AsyncMock(return_value=commands),
        ),
        patch("crestron_nvx.NvxClient.async_send_display_command", AsyncMock()) as send,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        for action, name in (
            ("power_on", "power on"),
            ("power_off", "power off"),
            ("input_control", "input control"),
        ):
            entity_id = registry.async_get_entity_id(
                "button", DOMAIN, f"{DEVICE_ID}_output1_display_{action}"
            )
            assert entity_id
            entry = registry.async_get(entity_id)
            assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
            assert entry.original_name == f"Output 1 device {name}"
        assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        send.assert_not_awaited()
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
