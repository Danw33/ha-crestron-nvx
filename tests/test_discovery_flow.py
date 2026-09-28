"""Exercise user discovery through HA's actual flow manager."""

from ipaddress import IPv4Network
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import CoreState
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.discovery import (
    DiscoveredDevice,
    DiscoveryBusyError,
    DiscoveryError,
)

from .conftest import DEVICE_ID, MOCK_DATA, SNAPSHOT
from .test_identity import ipv4_records, registered_entry

DEVICE = DiscoveredDevice(
    "192.0.2.10", "living-room", "DM-NVX-360", "7.1.0", "Jan 02 2025"
)
SIBLING = DiscoveredDevice("192.0.2.11", "office", "DM-NVX-350", "6.0.0", "Feb 03 2024")
PATH = "custom_components.crestron_nvx.config_flow"


async def start_scan(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "scan"}
    )


async def find_device(hass):
    result = await start_scan(hass)
    with patch(f"{PATH}.async_discover", AsyncMock(return_value=[DEVICE])):
        return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def select_device(hass):
    result = await find_device(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DEVICE.host}
    )


async def test_manual_menu(hass):
    with patch(f"{PATH}.async_discover") as discover:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "manual"}
        )
    assert result["step_id"] == "manual"
    assert CONF_HOST in result["data_schema"].schema
    discover.assert_not_called()


async def test_scan_form_does_not_send_packets(hass):
    with patch(f"{PATH}.async_discover") as discover:
        result = await start_scan(hass)
    assert result["step_id"] == "scan"
    discover.assert_not_called()


async def test_invalid_target_does_not_send_packets(hass):
    result = await start_scan(hass)
    with patch(f"{PATH}.async_discover") as discover:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"target": "192.0.0.0/16"}
        )
    assert result["errors"] == {"target": "invalid_target"}
    discover.assert_not_called()


@pytest.mark.parametrize(
    "exception,error",
    [
        (DiscoveryBusyError(), "discovery_busy"),
        (DiscoveryError(), "discovery_failed"),
        (None, "no_devices"),
    ],
)
async def test_search_errors(hass, exception, error):
    result = await start_scan(hass)
    with patch(
        f"{PATH}.async_discover", AsyncMock(side_effect=exception, return_value=[])
    ) as discover:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"target": "192.0.2.0/24"}
        )
    discover.assert_awaited_once_with(hass, IPv4Network("192.0.2.0/24"))
    assert result["errors"] == {"base": error}


async def test_display_and_confirm_then_use_rest_identity(hass):
    result = await find_device(hass)
    options = result["data_schema"].schema[CONF_HOST].config["options"]
    assert options[0] == {"value": DEVICE.host, "label": DEVICE.label}
    with patch(
        f"{PATH}._async_validate_input", AsyncMock(return_value=SNAPSHOT)
    ) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: DEVICE.host}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "connect"
        assert CONF_HOST not in result["data_schema"].schema
        assert result["description_placeholders"] == {
            "device": DEVICE.label,
            "firmware": "7.1.0",
            "build_date": "Jan 02 2025",
        }
        validate.assert_not_called()
        assert not hass.config_entries.async_entries(DOMAIN)
        with patch(
            "custom_components.crestron_nvx.async_setup_entry",
            AsyncMock(return_value=True),
        ):
            credentials = {
                key: value for key, value in MOCK_DATA.items() if key != CONF_HOST
            }
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], credentials
            )
    validate.assert_awaited_once_with(hass, {**MOCK_DATA, CONF_HOST: DEVICE.host})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_ID
    assert result["title"] == SNAPSHOT.device.name
    assert "firmware" not in result["data"]


def pending_discoveries(hass):
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == config_entries.SOURCE_INTEGRATION_DISCOVERY
    ]


async def scan_pair(hass):
    hass.set_state(CoreState.running)
    result = await start_scan(hass)
    with patch(f"{PATH}.async_discover", AsyncMock(return_value=[DEVICE, SIBLING])):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"target": "192.0.2.0/24"}
        )
    await hass.async_block_till_done()
    return result


@pytest.mark.parametrize("select_first", [False, True])
async def test_scan_publishes_before_selection_and_survives_cancel(hass, select_first):
    with patch(f"{PATH}._async_validate_input") as validate:
        result = await scan_pair(hass)
        assert result["step_id"] == "select_device"
        cards = pending_discoveries(hass)
        assert {card["context"]["unique_id"] for card in cards} == {
            f"udp41794:{DEVICE.host}",
            f"udp41794:{SIBLING.host}",
        }
        assert all(card["step_id"] == "connect" for card in cards)
        if select_first:
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: DEVICE.host}
            )
        hass.config_entries.flow.async_abort(result["flow_id"])
        assert pending_discoveries(hass) == cards
        assert not hass.config_entries.async_entries(DOMAIN)
        validate.assert_not_called()


async def test_repeated_scan_does_not_duplicate_cards(hass):
    result = await scan_pair(hass)
    cards = pending_discoveries(hass)
    hass.config_entries.flow.async_abort(result["flow_id"])
    await scan_pair(hass)
    assert pending_discoveries(hass) == cards


@pytest.mark.parametrize("from_card", [False, True])
async def test_setup_retires_only_matching_card(hass, from_card):
    result = await scan_pair(hass)
    if from_card:
        result = next(
            card
            for card in pending_discoveries(hass)
            if card["context"]["unique_id"] == f"udp41794:{DEVICE.host}"
        )
    else:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: DEVICE.host}
        )
    credentials = {key: value for key, value in MOCK_DATA.items() if key != CONF_HOST}
    with (
        patch(f"{PATH}._async_validate_input", AsyncMock(return_value=SNAPSHOT)),
        patch(
            "custom_components.crestron_nvx.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], credentials
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DEVICE_ID
    assert result["result"].data[CONF_HOST] == DEVICE.host
    assert [card["context"]["unique_id"] for card in pending_discoveries(hass)] == [
        f"udp41794:{SIBLING.host}"
    ]


async def test_delayed_discovery_for_configured_address_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN, data={**MOCK_DATA, CONF_HOST: DEVICE.host}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            CONF_HOST: DEVICE.host,
            "hostname": DEVICE.hostname,
            "model": DEVICE.model,
        },
    )
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "data",
    [
        {CONF_HOST: DEVICE.host},
        {
            CONF_HOST: "not-an-ip",
            "hostname": DEVICE.hostname,
            "model": DEVICE.model,
        },
        {
            CONF_HOST: DEVICE.host,
            "hostname": DEVICE.hostname,
            "model": "unsupported-model",
        },
    ],
)
async def test_discovery_rejects_invalid_candidate(hass, data):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data=data,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_discovery"


async def test_discovery_auth_failure_keeps_candidate(hass):
    from crestron_nvx import NvxAuthenticationError

    hass.set_state(CoreState.running)
    result = await select_device(hass)
    await hass.async_block_till_done()
    cards = pending_discoveries(hass)
    assert len(cards) == 1
    with patch(
        f"{PATH}._async_validate_input", AsyncMock(side_effect=NvxAuthenticationError)
    ):
        credentials = {
            key: value for key, value in MOCK_DATA.items() if key != CONF_HOST
        }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], credentials
        )
    assert result["step_id"] == "connect"
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"]["device"] == DEVICE.label
    assert pending_discoveries(hass) == cards


async def test_ignored_candidate_not_republished(hass):
    MockConfigEntry(
        domain=DOMAIN,
        source=config_entries.SOURCE_IGNORE,
        unique_id=f"udp41794:{DEVICE.host}",
        data={},
    ).add_to_hass(hass)
    await scan_pair(hass)
    assert [card["context"]["unique_id"] for card in pending_discoveries(hass)] == [
        f"udp41794:{SIBLING.host}"
    ]


async def test_filter_configured_ip(hass):
    MockConfigEntry(
        domain=DOMAIN, data={**MOCK_DATA, CONF_HOST: DEVICE.host}
    ).add_to_hass(hass)
    result = await find_device(hass)
    assert result["step_id"] == "scan"
    assert result["errors"] == {"base": "no_devices"}


async def test_device_configured_between_search_and_selection(hass):
    result = await find_device(hass)
    MockConfigEntry(
        domain=DOMAIN, data={**MOCK_DATA, CONF_HOST: DEVICE.host}
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DEVICE.host}
    )
    assert result["reason"] == "already_configured"


async def test_hostname_configured_device_deduplicates_after_auth(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id=DEVICE_ID)
    entry.add_to_hass(hass)
    result = await select_device(hass)
    with patch(f"{PATH}._async_validate_input", AsyncMock(return_value=SNAPSHOT)):
        credentials = {
            key: value for key, value in MOCK_DATA.items() if key != CONF_HOST
        }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], credentials
        )
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.data == MOCK_DATA


async def test_scan_filters_all_configured_hostname_addresses(hass, mock_ipv4_dns):
    mock_ipv4_dns.return_value = ipv4_records(DEVICE.host, SIBLING.host)
    MockConfigEntry(
        domain=DOMAIN, data=MOCK_DATA, unique_id=DEVICE_ID, title="Living Room TV"
    ).add_to_hass(hass)
    with patch(f"{PATH}._async_validate_input") as validate:
        result = await scan_pair(hass)
    assert result["errors"] == {"base": "no_devices"}
    assert not pending_discoveries(hass)
    validate.assert_not_called()


async def test_rescan_removes_cards_now_known_by_hostname(hass, mock_ipv4_dns):
    result = await scan_pair(hass)
    hass.config_entries.flow.async_abort(result["flow_id"])
    MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id=DEVICE_ID).add_to_hass(
        hass
    )
    mock_ipv4_dns.return_value = ipv4_records(DEVICE.host)
    result = await scan_pair(hass)
    assert result["step_id"] == "select_device"
    assert [card["context"]["unique_id"] for card in pending_discoveries(hass)] == [
        f"udp41794:{SIBLING.host}"
    ]


async def test_selected_candidate_now_configured_by_hostname(hass, mock_ipv4_dns):
    result = await find_device(hass)
    MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id=DEVICE_ID).add_to_hass(
        hass
    )
    mock_ipv4_dns.return_value = ipv4_records(DEVICE.host)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: DEVICE.host}
    )
    assert result["reason"] == "already_configured"


async def test_delayed_card_filters_configured_hostname(hass, mock_ipv4_dns):
    MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id=DEVICE_ID).add_to_hass(
        hass
    )
    mock_ipv4_dns.return_value = ipv4_records(DEVICE.host)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_INTEGRATION_DISCOVERY},
        data={
            CONF_HOST: DEVICE.host,
            "hostname": DEVICE.hostname,
            "model": DEVICE.model,
        },
    )
    assert result["reason"] == "already_configured"


async def test_equal_udp_names_do_not_merge_unknown_devices(hass):
    from dataclasses import replace

    hass.set_state(CoreState.running)
    result = await start_scan(hass)
    with patch(
        f"{PATH}.async_discover",
        AsyncMock(return_value=[DEVICE, replace(DEVICE, host=SIBLING.host)]),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert len(pending_discoveries(hass)) == 2
    assert len(result["data_schema"].schema[CONF_HOST].config["options"]) == 3


async def test_manual_hostname_setup_retires_all_resolved_cards(hass, mock_ipv4_dns):
    result = await scan_pair(hass)
    hass.config_entries.flow.async_abort(result["flow_id"])
    mock_ipv4_dns.return_value = ipv4_records(DEVICE.host, SIBLING.host)
    with (
        patch(f"{PATH}._async_validate_input", AsyncMock(return_value=SNAPSHOT)),
        patch(
            "custom_components.crestron_nvx.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=MOCK_DATA
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not pending_discoveries(hass)


async def test_authenticated_alternate_interface_serial_preserves_existing_entry(hass):
    entry = registered_entry(hass)
    result = await select_device(hass)
    with patch(f"{PATH}._async_validate_input", AsyncMock(return_value=SNAPSHOT)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {key: val for key, val in MOCK_DATA.items() if key != CONF_HOST},
        )
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "original"
    assert entry.data == MOCK_DATA
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_select_manual_fallback(hass):
    result = await find_device(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "manual"}
    )
    assert result["step_id"] == "manual"


async def test_invalid_selection(hass):
    result = await find_device(hass)
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    result = await flow.async_step_select_device({CONF_HOST: "198.51.100.1"})
    assert result["errors"] == {"base": "invalid_selection"}
