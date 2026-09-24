"""Tests for the endpoint coordinator."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from crestron_nvx import (
    NvxAuthenticationError,
    NvxConnectionError,
    NvxPreviewInfo,
    NvxResponseError,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.coordinator import CrestronNvxCoordinator

from .conftest import SNAPSHOT


async def test_update_success(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Return a typed snapshot from the client."""

    client = MagicMock(
        async_get_snapshot=AsyncMock(return_value=SNAPSHOT),
        async_get_preview_info=AsyncMock(return_value=NvxPreviewInfo()),
    )
    coordinator = CrestronNvxCoordinator(hass, mock_config_entry, client)
    assert await coordinator._async_update_data() == SNAPSHOT


@pytest.mark.parametrize("error", [NvxConnectionError(), NvxResponseError()])
async def test_update_failure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, error: Exception
) -> None:
    """Convert expected client failures to coordinator failures."""

    client = MagicMock(async_get_snapshot=AsyncMock(side_effect=error))
    coordinator = CrestronNvxCoordinator(hass, mock_config_entry, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_update_auth_failure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Start reauthentication when a session cannot authenticate."""

    client = MagicMock(
        async_get_snapshot=AsyncMock(side_effect=NvxAuthenticationError())
    )
    coordinator = CrestronNvxCoordinator(hass, mock_config_entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
