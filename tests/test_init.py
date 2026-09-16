"""Tests for config-entry lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx import async_setup_entry, async_unload_entry


async def test_setup_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Set up, refresh, and forward all platforms."""

    coordinator = MagicMock(async_config_entry_first_refresh=AsyncMock())
    with (
        patch(
            "custom_components.crestron_nvx.CrestronNvxCoordinator",
            return_value=coordinator,
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
        ) as forward,
    ):
        assert await async_setup_entry(hass, mock_config_entry)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert mock_config_entry.runtime_data is coordinator
    forward.assert_awaited_once()


async def test_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Unload every forwarded platform."""

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new=AsyncMock(return_value=True),
    ) as unload:
        assert await async_unload_entry(hass, mock_config_entry)
    unload.assert_awaited_once()
