"""Stream commands are disabled, direction-bound and never run on lifecycle events."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxControlError,
    NvxControlUnsupported,
    NvxPermissionError,
    NvxStream,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.crestron_nvx.button import NvxStreamButton, async_setup_entry
from custom_components.crestron_nvx.const import DOMAIN

from .conftest import DEVICE_ID, SNAPSHOT
from .test_switch import coordinator


def snapshot(direction="receive", status="Stream started"):
    return replace(
        SNAPSHOT,
        device_mode="Receiver" if direction == "receive" else "Transmitter",
        **{
            f"{direction}_streams": (
                NvxStream(
                    "slot0",
                    direction,
                    slot_index=0,
                    status=status,
                    processing=False,
                    stream_location="rtsp://192.0.2.20/live.sdp",
                ),
            )
        },
    )


def stream_coordinator(hass, entry, direction="receive"):
    coord = coordinator(hass, entry)
    coord.async_set_updated_data(snapshot(direction))
    coord.client.async_set_stream_running = AsyncMock(
        return_value=snapshot(direction, "Stream stopped")
    )
    return coord


@pytest.mark.parametrize("direction", ["receive", "transmit"])
@pytest.mark.parametrize("running", [True, False])
async def test_explicit_action_properties_and_observed_state(
    hass, mock_config_entry, direction, running
):
    coord = stream_coordinator(hass, mock_config_entry, direction)
    button = NvxStreamButton(coord, direction, running)
    action = "start" if running else "stop"
    assert button.unique_id == f"{DEVICE_ID}_{direction}_stream_0_{action}_control"
    assert button.translation_key == f"{direction}_stream_{action}"
    assert not button.entity_registry_enabled_default
    assert button.entity_category is None  # Operational action, not configuration.
    result = snapshot(direction, "Stream started" if running else "Stream stopped")
    coord.client.async_set_stream_running.return_value = result
    await button.async_press()
    coord.client.async_set_stream_running.assert_awaited_once_with(
        direction, running, expected_device_id=DEVICE_ID
    )
    assert coord.data == result


@pytest.mark.parametrize("direction", ["receive", "transmit"])
async def test_setup_only_current_direction_and_no_commands(
    hass, mock_config_entry, direction
):
    coord = stream_coordinator(hass, mock_config_entry, direction)
    mock_config_entry.runtime_data = coord
    add = MagicMock()
    await async_setup_entry(hass, mock_config_entry, add)
    buttons = [
        entity
        for entity in add.call_args.args[0]
        if isinstance(entity, NvxStreamButton)
    ]
    assert len(buttons) == 2
    assert all(entity.translation_key.startswith(direction) for entity in buttons)
    coord.client.async_set_stream_running.assert_not_awaited()


@pytest.mark.parametrize("change", ["busy", "missing", "mode", "offline"])
async def test_unavailable_never_commands(hass, mock_config_entry, change):
    coord = stream_coordinator(hass, mock_config_entry)
    button = NvxStreamButton(coord, "receive", False)
    if change == "busy":
        coord.async_set_updated_data(
            replace(
                coord.data,
                receive_streams=(
                    replace(coord.data.receive_streams[0], processing=True),
                ),
            )
        )
    elif change == "missing":
        coord.async_set_updated_data(replace(coord.data, receive_streams=()))
    elif change == "mode":
        coord.async_set_updated_data(replace(coord.data, device_mode="Transmitter"))
    else:
        coord.last_update_success = False
    assert not button.available
    with pytest.raises(ServiceValidationError):
        await button.async_press()
    coord.client.async_set_stream_running.assert_not_awaited()


@pytest.mark.parametrize(
    "error,expected",
    [
        (NvxControlUnsupported(), ServiceValidationError),
        (NvxPermissionError(), HomeAssistantError),
        (NvxControlError(), HomeAssistantError),
        (NvxAuthenticationError(), HomeAssistantError),
    ],
)
async def test_failure_keeps_observed_state(hass, mock_config_entry, error, expected):
    coord = stream_coordinator(hass, mock_config_entry)
    before = coord.data
    coord.client.async_set_stream_running.side_effect = error
    button = NvxStreamButton(coord, "receive", False)
    button.hass = hass
    with (
        patch.object(mock_config_entry, "async_start_reauth") as reauth,
        pytest.raises(expected),
    ):
        await button.async_press()
    assert reauth.call_count == int(isinstance(error, NvxAuthenticationError))
    assert coord.data == before
    assert coord.last_update_success


async def test_enable_press_reload_unload_never_restores_stream(
    hass, mock_config_entry, mock_client
):
    with (
        patch(
            "custom_components.crestron_nvx.NvxClient.async_get_snapshot",
            return_value=snapshot(),
        ),
        patch(
            "crestron_nvx.NvxClient.async_set_stream_running",
            new_callable=AsyncMock,
            return_value=snapshot(status="Stream stopped"),
        ) as command,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "button", DOMAIN, f"{DEVICE_ID}_receive_stream_0_stop_control"
        )
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        command.assert_not_awaited()
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
        command.assert_awaited_once_with("receive", False, expected_device_id=DEVICE_ID)
        assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        assert command.await_count == 1


async def test_poll_serialization_and_cancellation(hass, mock_config_entry):
    coord = stream_coordinator(hass, mock_config_entry)
    entered, release = asyncio.Event(), asyncio.Event()

    async def read():
        entered.set()
        await release.wait()
        return snapshot()

    coord.client.async_get_snapshot.side_effect = read
    poll = asyncio.create_task(coord.async_refresh())
    await entered.wait()
    command = asyncio.create_task(coord.async_set_stream_running("receive", False))
    await asyncio.sleep(0)
    coord.client.async_set_stream_running.assert_not_awaited()
    release.set()
    await asyncio.gather(poll, command)
    coord.client.async_set_stream_running.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await coord.async_set_stream_running("receive", True)
    assert not coord._operation_lock.locked()
