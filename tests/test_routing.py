"""Routing uses fresh authenticated transmitters and never writes on discovery."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxControlError,
    NvxControlUnsupported,
    NvxStream,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx import async_setup_entry, async_unload_entry
from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.crestron_nvx.routing import (
    NvxReceiverStreamSelect,
    primary_transmit_location,
)

from .conftest import DEVICE_ID, MOCK_DATA, SNAPSHOT
from .test_switch import coordinator

URL = "rtsp://192.0.2.20:554/live.sdp"
RX = replace(
    SNAPSHOT,
    receive_streams=(
        NvxStream(
            "receive_0",
            "receive",
            slot_index=0,
            stream_location="",
            processing=False,
            session_initiation="Multicast via RTSP",
        ),
    ),
)
TX = replace(
    SNAPSHOT,
    device=replace(SNAPSHOT.device, device_id="transmitter", name="Garage"),
    device_mode="Transmitter",
    transmit_streams=(
        NvxStream(
            "tx", "transmit", slot_index=0, stream_location=URL, processing=False
        ),
    ),
)


def pair(hass, entry):
    rx = coordinator(hass, entry)
    rx.async_set_updated_data(RX)
    rx.client.async_set_receive_stream_location = AsyncMock(
        return_value=replace(
            RX, receive_streams=(replace(RX.receive_streams[0], stream_location=URL),)
        )
    )
    tx_entry = MockConfigEntry(
        domain=DOMAIN, title="Garage", unique_id="transmitter", data=MOCK_DATA
    )
    tx_entry.add_to_hass(hass)
    tx = coordinator(hass, tx_entry)
    tx.async_set_updated_data(TX)
    tx.client.async_get_snapshot.return_value = TX
    hass.data[DOMAIN] = {entry.entry_id: rx, tx_entry.entry_id: tx}
    entry.runtime_data = rx
    return rx, tx, NvxReceiverStreamSelect(rx)


async def test_properties_and_fresh_verified_write(hass, mock_config_entry):
    rx, tx, entity = pair(hass, mock_config_entry)
    assert entity.unique_id == f"{DEVICE_ID}_receiver_stream_control"
    assert not entity.entity_registry_enabled_default
    assert entity.entity_category is EntityCategory.CONFIG
    assert entity.options == ["Garage (transmitter)"]
    assert entity.current_option is None
    await entity.async_select_option(entity.options[0])
    tx.client.async_get_snapshot.assert_awaited_once()
    rx.client.async_set_receive_stream_location.assert_awaited_once_with(
        URL, expected_device_id=DEVICE_ID
    )
    assert entity.current_option == entity.options[0]
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert URL not in repr(result)


async def test_dynamic_sources_and_names(hass, mock_config_entry):
    rx, tx, entity = pair(hass, mock_config_entry)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=tx.config_entry.entry_id, identifiers={(DOMAIN, "transmitter")}
    )
    registry.async_update_device(device.id, name_by_user="My source")
    assert entity.options == ["My source (transmitter)"]
    tx.last_update_success = False
    assert entity.options == []
    assert not entity.available
    tx.last_update_success = True
    tx.async_set_updated_data(replace(TX, device_mode="Receiver"))
    assert entity.options == []
    tx.async_set_updated_data(replace(TX, device=SNAPSHOT.device))
    assert entity.options == []
    tx.async_set_updated_data(TX)
    other_entry = MockConfigEntry(
        domain=DOMAIN, title="My source", unique_id="second", data=MOCK_DATA
    )
    other_entry.add_to_hass(hass)
    other = coordinator(hass, other_entry)
    other.async_set_updated_data(
        replace(TX, device=replace(TX.device, device_id="second"))
    )
    hass.data[DOMAIN][other_entry.entry_id] = other
    assert len(entity.options) == 2
    rx.async_set_updated_data(
        replace(
            RX, receive_streams=(replace(RX.receive_streams[0], stream_location=URL),)
        )
    )
    assert entity.current_option is None  # Ambiguous advertised URL is not guessed.
    hass.data[DOMAIN].pop(other_entry.entry_id)
    assert entity.current_option == "My source (transmitter)"
    rx.async_set_updated_data(SNAPSHOT)
    assert entity.current_option is None
    assert not entity.available


@pytest.mark.parametrize(
    "snapshot",
    [
        replace(TX, device_mode="Receiver"),
        replace(TX, transmit_streams=()),
        replace(
            TX, transmit_streams=(replace(TX.transmit_streams[0], processing=True),)
        ),
        replace(
            TX,
            transmit_streams=(
                replace(TX.transmit_streams[0], stream_location="https://bad/"),
            ),
        ),
    ],
)
def test_ineligible_transmitter(snapshot):
    assert primary_transmit_location(snapshot) is None


async def test_stale_choice_removed_and_identity_mismatch(hass, mock_config_entry):
    rx, tx, entity = pair(hass, mock_config_entry)
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option("Not a configured transmitter")
    tx.client.async_get_snapshot.return_value = replace(
        TX, device=replace(TX.device, device_id="wrong")
    )
    with pytest.raises(HomeAssistantError):
        await entity.async_select_option(entity.options[0])
    assert tx.data == TX  # Wrong endpoint never becomes the configured device state.
    rx.client.async_set_receive_stream_location.assert_not_awaited()


@pytest.mark.parametrize("error", [NvxAuthenticationError(), NvxControlError()])
async def test_source_error_never_writes_receiver(hass, mock_config_entry, error):
    rx, tx, entity = pair(hass, mock_config_entry)
    entity.hass = hass
    tx.client.async_get_snapshot.side_effect = error
    with (
        patch.object(tx.config_entry, "async_start_reauth") as reauth,
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_select_option(entity.options[0])
    assert reauth.call_count == int(isinstance(error, NvxAuthenticationError))
    rx.client.async_set_receive_stream_location.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [NvxAuthenticationError(), NvxControlUnsupported(), NvxControlError()]
)
async def test_receiver_errors_preserve_state(hass, mock_config_entry, error):
    rx, _, entity = pair(hass, mock_config_entry)
    entity.hass = hass
    rx.client.async_set_receive_stream_location.side_effect = error
    with (
        patch.object(mock_config_entry, "async_start_reauth") as reauth,
        pytest.raises(HomeAssistantError),
    ):
        await entity.async_select_option(entity.options[0])
    assert reauth.call_count == int(isinstance(error, NvxAuthenticationError))
    assert rx.data == RX


async def test_source_changes_mode_or_unloads_during_refresh(hass, mock_config_entry):
    rx, tx, entity = pair(hass, mock_config_entry)
    tx.client.async_get_snapshot.return_value = replace(TX, device_mode="Receiver")
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option(entity.options[0])
    tx.async_set_updated_data(TX)

    async def removed():
        hass.data[DOMAIN].pop(tx.config_entry.entry_id)
        return TX

    tx.client.async_get_snapshot.side_effect = removed
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option(entity.options[0])
    rx.client.async_set_receive_stream_location.assert_not_awaited()


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_setup_failure_removes_catalog_entry(
    hass, mock_config_entry, mock_client, error
):
    with (
        patch(
            "custom_components.crestron_nvx.CrestronNvxCoordinator.async_config_entry_first_refresh"
        ),
        patch("custom_components.crestron_nvx.async_migrate_port_entities"),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", side_effect=error
        ),
        pytest.raises(error),
    ):
        await async_setup_entry(hass, mock_config_entry)
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_route_serializes_with_polling_and_cancellation_releases_lock(
    hass, mock_config_entry
):
    rx, _, _ = pair(hass, mock_config_entry)
    rx.client.async_get_snapshot.return_value = RX
    entered, release = asyncio.Event(), asyncio.Event()

    async def read():
        entered.set()
        await release.wait()
        return RX

    rx.client.async_get_snapshot.side_effect = read
    poll = asyncio.create_task(rx.async_refresh())
    await entered.wait()
    command = asyncio.create_task(rx.async_set_receive_stream_location(URL))
    await asyncio.sleep(0)
    rx.client.async_set_receive_stream_location.assert_not_awaited()
    release.set()
    await asyncio.gather(poll, command)
    rx.client.async_set_receive_stream_location.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await rx.async_set_receive_stream_location(URL)
    assert not rx._operation_lock.locked()


async def test_failed_unload_preserves_catalog(hass, mock_config_entry):
    rx, _, _ = pair(hass, mock_config_entry)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await async_unload_entry(hass, mock_config_entry)
    assert hass.data[DOMAIN][mock_config_entry.entry_id] is rx


async def test_enable_service_update_unload_without_lifecycle_writes(
    hass, mock_config_entry, mock_client
):
    with (
        patch(
            "custom_components.crestron_nvx.NvxClient.async_get_snapshot",
            return_value=RX,
        ),
        patch(
            "crestron_nvx.NvxClient.async_set_receive_stream_location",
            new_callable=AsyncMock,
            return_value=replace(
                RX,
                receive_streams=(replace(RX.receive_streams[0], stream_location=URL),),
            ),
        ) as write,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        actual = mock_config_entry.runtime_data
        _, tx, _ = pair(hass, mock_config_entry)
        mock_config_entry.runtime_data = actual
        hass.data[DOMAIN][mock_config_entry.entry_id] = actual
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "select", DOMAIN, f"{DEVICE_ID}_receiver_stream_control"
        )
        assert (
            registry.async_get(entity_id).disabled_by
            is er.RegistryEntryDisabler.INTEGRATION
        )
        registry.async_update_entity(entity_id, disabled_by=None)
        assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        write.assert_not_awaited()
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "Garage (transmitter)"},
            blocking=True,
        )
        write.assert_awaited_once_with(URL, expected_device_id=DEVICE_ID)
        tx.async_set_updated_data(replace(TX, device_mode="Receiver"))
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "unavailable"
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]
        tx.async_set_updated_data(TX)
        await hass.async_block_till_done()
