"""Tests for privacy-safe diagnostics."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import DEVICE_ID, HOST, SNAPSHOT


async def test_diagnostics_redact_endpoint_identity(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Exclude credentials and network/device identifiers."""

    coordinator = MagicMock(
        data=SNAPSHOT,
        last_update_success=True,
        last_exception=None,
    )
    mock_config_entry.runtime_data = coordinator
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    serialized = repr(result)
    assert DEVICE_ID not in serialized
    assert HOST not in serialized
    assert "test-password" not in serialized
    assert "input-port" not in serialized
    assert "transmit-id" not in serialized
    assert "HDMI input" not in serialized
    assert result["snapshot"]["device"]["model"] == "DM-NVX-350"
    assert "raw_device_specific" not in result["snapshot"]
    assert result["last_exception_type"] is None


async def test_diagnostics_include_exception_type(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Include only the safe exception type."""

    mock_config_entry.runtime_data = MagicMock(
        data=SNAPSHOT,
        last_update_success=False,
        last_exception=RuntimeError("private detail"),
    )
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert result["last_exception_type"] == "RuntimeError"
    assert "private detail" not in repr(result)
