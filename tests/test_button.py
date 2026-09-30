"""Reboot remains an explicit, disabled diagnostic action."""

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
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.button import NvxRebootButton, async_setup_entry
from custom_components.crestron_nvx.const import DOMAIN

from .conftest import DEVICE_ID, SNAPSHOT
from .test_switch import coordinator


def reboot_coordinator(hass, entry):
    coord = coordinator(hass, entry)
    coord.client.async_reboot = AsyncMock()
    return coord


async def test_button_is_disabled_diagnostic_with_stable_identity(
    hass, mock_config_entry
):
    coord = reboot_coordinator(hass, mock_config_entry)
    button = NvxRebootButton(coord)
    assert button.unique_id == f"{DEVICE_ID}_reboot_control"
    assert button.entity_category is EntityCategory.DIAGNOSTIC
    assert button.device_class is ButtonDeviceClass.RESTART
    assert button.entity_registry_enabled_default is False
    await button.async_press()
    coord.client.async_reboot.assert_awaited_once_with(expected_device_id=DEVICE_ID)


async def test_unknown_model_or_unavailable_endpoint_cannot_reboot(
    hass, mock_config_entry
):
    coord = reboot_coordinator(hass, mock_config_entry)
    mock_config_entry.runtime_data = coord
    add = MagicMock()
    coord.async_set_updated_data(
        replace(SNAPSHOT, device=replace(SNAPSHOT.device, model="Unknown"))
    )
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_not_called()
    coord.async_set_updated_data(SNAPSHOT)
    await async_setup_entry(hass, mock_config_entry, add)
    add.assert_called_once()
    button = NvxRebootButton(coord)
    with (
        patch.object(type(button), "available", False),
        pytest.raises(ServiceValidationError),
    ):
        await button.async_press()
    coord.client.async_reboot.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (NvxControlUnsupported(), ServiceValidationError),
        (NvxPermissionError(), HomeAssistantError),
        (NvxControlError(), HomeAssistantError),
        (NvxAuthenticationError(), HomeAssistantError),
    ],
)
async def test_command_failures_preserve_monitoring(
    hass, mock_config_entry, error, expected
):
    coord = reboot_coordinator(hass, mock_config_entry)
    coord.client.async_reboot.side_effect = error
    button = NvxRebootButton(coord)
    button.hass = hass
    with (
        patch.object(mock_config_entry, "async_start_reauth") as reauth,
        pytest.raises(expected),
    ):
        await button.async_press()
    assert reauth.call_count == int(isinstance(error, NvxAuthenticationError))
    assert coord.last_update_success


async def test_registry_setup_reload_do_not_reboot(
    hass, mock_config_entry, mock_client
):
    with patch("crestron_nvx.NvxClient.async_reboot", new_callable=AsyncMock) as reboot:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "button", DOMAIN, f"{DEVICE_ID}_reboot_control"
        )
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        reboot.assert_not_awaited()
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
        reboot.assert_awaited_once_with(expected_device_id=DEVICE_ID)
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_poll_is_serialized_with_reboot(hass, mock_config_entry):
    coord = reboot_coordinator(hass, mock_config_entry)
    entered, release = asyncio.Event(), asyncio.Event()

    async def preview():
        entered.set()
        await release.wait()
        return NvxPreviewInfo()

    coord.client.async_get_preview_info.side_effect = preview
    poll = asyncio.create_task(coord.async_refresh())
    await entered.wait()
    command = asyncio.create_task(coord.async_reboot())
    await asyncio.sleep(0)
    coord.client.async_reboot.assert_not_awaited()
    release.set()
    await asyncio.gather(poll, command)
    assert not coord._operation_lock.locked()
