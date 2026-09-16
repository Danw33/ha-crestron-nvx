"""Tests for the Crestron DM NVX config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from crestron_nvx import (
    NvxApiError,
    NvxAuthenticationError,
    NvxConnectionError,
    NvxResponseError,
)
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.config_flow import _async_validate_input
from custom_components.crestron_nvx.const import CONF_VERIFY_SSL, DOMAIN

from .conftest import DEVICE_ID, MOCK_DATA, SNAPSHOT


async def test_user_form(hass: HomeAssistant) -> None:
    """Show the initial form."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_validate_input_uses_injected_ha_session(hass: HomeAssistant) -> None:
    """Construct the client with Home Assistant's shared web session."""
    session = MagicMock()
    with (
        patch(
            "custom_components.crestron_nvx.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch("custom_components.crestron_nvx.config_flow.NvxClient") as client_class,
    ):
        client_class.return_value.async_get_snapshot = AsyncMock(return_value=SNAPSHOT)

        assert await _async_validate_input(hass, MOCK_DATA) is SNAPSHOT

    client_class.assert_called_once_with(
        session,
        MOCK_DATA[CONF_HOST],
        MOCK_DATA[CONF_USERNAME],
        MOCK_DATA[CONF_PASSWORD],
        verify_ssl=MOCK_DATA[CONF_VERIFY_SSL],
    )


async def test_user_success(hass: HomeAssistant) -> None:
    """Create an entry after validating a read-only snapshot."""

    with (
        patch(
            "custom_components.crestron_nvx.config_flow._async_validate_input",
            new=AsyncMock(return_value=SNAPSHOT),
        ),
        patch(
            "custom_components.crestron_nvx.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={**MOCK_DATA, CONF_HOST: " NVX.EXAMPLE.LOCAL "},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Synthetic NVX"
    assert result["data"][CONF_HOST] == "nvx.example.local"
    assert result["result"].unique_id == DEVICE_ID


@pytest.mark.parametrize(
    ("error", "flow_error"),
    [
        (NvxAuthenticationError(), "invalid_auth"),
        (NvxConnectionError(), "cannot_connect"),
        (NvxResponseError(), "invalid_response"),
        (NvxApiError(), "unknown"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_user_errors(
    hass: HomeAssistant, error: Exception, flow_error: str
) -> None:
    """Map endpoint validation failures to translated flow errors."""

    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(side_effect=error),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=MOCK_DATA,
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": flow_error}


async def test_invalid_host(hass: HomeAssistant) -> None:
    """Reject a malformed host before network access."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={**MOCK_DATA, CONF_HOST: "bad host/path"},
    )
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_duplicate_updates_host(hass: HomeAssistant) -> None:
    """Abort duplicates while updating a discovered address."""

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(return_value=SNAPSHOT),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={**MOCK_DATA, CONF_HOST: "new.example.local"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "new.example.local"


async def test_reauth_success(hass: HomeAssistant) -> None:
    """Update valid replacement credentials."""

    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(return_value=SNAPSHOT),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "new-password"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_USERNAME] == "new-user"


async def test_reauth_wrong_device(hass: HomeAssistant) -> None:
    """Refuse credentials that resolve to a different physical endpoint."""

    entry = MockConfigEntry(domain=DOMAIN, unique_id="other", data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(return_value=SNAPSHOT),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "new-password"},
        )
    assert result["reason"] == "wrong_device"


@pytest.mark.parametrize(
    ("error", "flow_error"),
    [
        (NvxAuthenticationError(), "invalid_auth"),
        (NvxConnectionError(), "cannot_connect"),
        (NvxResponseError(), "cannot_connect"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_reauth_errors(
    hass: HomeAssistant, error: Exception, flow_error: str
) -> None:
    """Keep reauthentication open after validation failures."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(side_effect=error),
    ):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "new-user", CONF_PASSWORD: "wrong"},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": flow_error}


async def _start_reconfigure(
    hass: HomeAssistant, entry: MockConfigEntry
) -> config_entries.ConfigFlowResult:
    """Start a reconfiguration flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )


async def test_reconfigure_success(hass: HomeAssistant) -> None:
    """Update connection data after verifying the same endpoint."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(return_value=SNAPSHOT),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {**MOCK_DATA, CONF_HOST: " NEW.EXAMPLE.LOCAL "},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "new.example.local"


async def test_reconfigure_wrong_device(hass: HomeAssistant) -> None:
    """Refuse to repoint an entry at different hardware."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="other", data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(return_value=SNAPSHOT),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], MOCK_DATA
        )
    assert result["reason"] == "wrong_device"


@pytest.mark.parametrize(
    ("error", "flow_error"),
    [
        (NvxAuthenticationError(), "invalid_auth"),
        (NvxConnectionError(), "cannot_connect"),
        (NvxResponseError(), "invalid_response"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_reconfigure_errors(
    hass: HomeAssistant, error: Exception, flow_error: str
) -> None:
    """Keep reconfiguration open after validation failures."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.crestron_nvx.config_flow._async_validate_input",
        new=AsyncMock(side_effect=error),
    ):
        result = await _start_reconfigure(hass, entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], MOCK_DATA
        )
    assert result["errors"] == {"base": flow_error}


async def test_reconfigure_invalid_host(hass: HomeAssistant) -> None:
    """Reject a malformed replacement host."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DEVICE_ID, data=MOCK_DATA)
    entry.add_to_hass(hass)
    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**MOCK_DATA, CONF_HOST: "not a host/path"}
    )
    assert result["errors"] == {CONF_HOST: "invalid_host"}
