"""Preview isolation, capability discovery, caching and lifecycle tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import NvxConnectionError, NvxPreviewImage, NvxPreviewInfo

from custom_components.crestron_nvx.coordinator import CrestronNvxCoordinator
from custom_components.crestron_nvx.image import (
    NvxPreviewImageEntity,
    async_setup_entry,
)

from .conftest import DEVICE_ID, SNAPSHOT


def coordinator():
    value = MagicMock(data=SNAPSHOT, last_update_success=True)
    value.preview_info = NvxPreviewInfo(True, True, "/preview/test.jpeg")
    value.client.configuration_url = "https://nvx.example.local"
    value.client.async_get_preview = AsyncMock(
        return_value=NvxPreviewImage(b"jpeg", 32, 16)
    )
    return value


async def test_discovery_after_firmware_change(hass):
    co = coordinator()
    co.preview_info = NvxPreviewInfo()
    entry = MagicMock(runtime_data=co)
    add = MagicMock()
    await async_setup_entry(hass, entry, add)
    add.assert_not_called()
    discover = co.async_add_listener.call_args.args[0]
    co.preview_info = NvxPreviewInfo(True, False)
    discover()
    discover()
    add.assert_called_once()
    entity = add.call_args.args[0][0]
    assert entity.unique_id == f"{DEVICE_ID}_preview"
    assert not entity.available
    assert await entity.async_image() is None
    entry.async_on_unload.assert_called_once()


async def test_image_cache_and_recovery(hass):
    co = coordinator()
    entity = NvxPreviewImageEntity(hass, co)
    with patch("custom_components.crestron_nvx.image.monotonic", return_value=100):
        assert await asyncio.gather(entity.async_image(), entity.async_image()) == [
            b"jpeg",
            b"jpeg",
        ]
    co.client.async_get_preview.assert_awaited_once()
    assert entity.image_last_updated is not None
    co.client.async_get_preview.side_effect = NvxConnectionError()
    with patch("custom_components.crestron_nvx.image.monotonic", return_value=131):
        assert await entity.async_image() is None
        assert await entity.async_image() is None
    assert co.client.async_get_preview.await_count == 2
    co.client.async_get_preview.side_effect = None
    entity.entity_id = "image.synthetic_preview"
    with patch.object(entity, "async_write_ha_state") as write:
        with patch("custom_components.crestron_nvx.image.monotonic", return_value=162):
            assert await entity.async_image() == b"jpeg"
        write.assert_called_once()
        co.preview_info = NvxPreviewInfo(True, False)
        entity._handle_coordinator_update()
        assert entity._frame is None
        co.preview_info = NvxPreviewInfo(True, True, "/preview/test.jpeg")
        entity._handle_coordinator_update()
    await entity.async_will_remove_from_hass()
    assert entity._frame is None


@pytest.mark.parametrize("error", [NvxConnectionError(), None])
async def test_optional_preview_cannot_break_status(hass, mock_config_entry, error):
    client = MagicMock(
        async_get_snapshot=AsyncMock(return_value=SNAPSHOT),
        async_get_preview_info=AsyncMock(
            return_value=NvxPreviewInfo(True, False), side_effect=error
        ),
    )
    co = CrestronNvxCoordinator(hass, mock_config_entry, client)
    assert await co._async_update_data() == SNAPSHOT
    assert co.preview_info.supported == (error is None)


@pytest.mark.parametrize("supported", [True, False])
async def test_real_platform_lifecycle(hass, mock_config_entry, mock_client, supported):
    """Exercise actual platform forwarding, entity registration and unloading."""
    with patch(
        "crestron_nvx.NvxClient.async_get_preview_info",
        return_value=NvxPreviewInfo(
            supported, supported, "/preview/test.jpeg" if supported else None
        ),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        images = hass.states.async_all("image")
        assert len(images) == int(supported)
        assert hass.states.async_all("sensor")
        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert all(
            state.state == "unavailable" and state.attributes.get("restored")
            for state in hass.states.async_all("image")
        )
