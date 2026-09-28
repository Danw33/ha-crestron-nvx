"""IPv4 address hints and authenticated physical identity are separate."""

import asyncio
import socket
from dataclasses import replace

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.const import DOMAIN
from custom_components.crestron_nvx.identity import (
    async_configured_addresses,
    async_ipv4_addresses,
    authenticated_entry,
)

from .conftest import MOCK_DATA, SNAPSHOT


def ipv4_records(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in addresses]


async def test_resolve_all_ipv4_addresses(hass, mock_ipv4_dns):
    mock_ipv4_dns.return_value = ipv4_records("192.0.2.10", "192.0.2.11", "192.0.2.10")
    assert await async_ipv4_addresses(hass, " NVX.Example.Local. ") == {
        "192.0.2.10",
        "192.0.2.11",
    }
    mock_ipv4_dns.assert_awaited_once_with(
        "nvx.example.local", None, family=socket.AF_INET, type=socket.SOCK_STREAM
    )


@pytest.mark.parametrize(
    "host,expected", [("192.0.2.10", {"192.0.2.10"}), ("2001:db8::10", set())]
)
async def test_literal_addresses_do_not_resolve(hass, mock_ipv4_dns, host, expected):
    assert await async_ipv4_addresses(hass, host) == expected
    mock_ipv4_dns.assert_not_awaited()


@pytest.mark.parametrize("error", [socket.gaierror(), TimeoutError()])
async def test_dns_failure_is_nonfatal(hass, mock_ipv4_dns, error):
    mock_ipv4_dns.side_effect = error
    assert await async_ipv4_addresses(hass, "nvx.example.local") == set()


async def test_dns_cancellation_propagates(hass, mock_ipv4_dns):
    mock_ipv4_dns.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await async_ipv4_addresses(hass, "nvx.example.local")


async def test_configured_addresses_ignore_titles_and_empty_entries(
    hass, mock_ipv4_dns
):
    mock_ipv4_dns.return_value = ipv4_records("192.0.2.10", "192.0.2.11")
    for host in ["nvx.example.local", "192.0.2.12", ""]:
        MockConfigEntry(
            domain=DOMAIN, title="Living Room TV", data={"host": host}
        ).add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, data={}).add_to_hass(hass)
    assert await async_configured_addresses(hass) == {
        "192.0.2.10",
        "192.0.2.11",
        "192.0.2.12",
    }
    mock_ipv4_dns.assert_awaited_once()


async def test_dns_lookup_really_times_out(hass, mock_ipv4_dns, monkeypatch):
    monkeypatch.setattr("custom_components.crestron_nvx.identity._DNS_TIMEOUT", 0.01)

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    mock_ipv4_dns.side_effect = stalled
    assert await async_ipv4_addresses(hass, "nvx.example.local") == set()
    mock_ipv4_dns.side_effect = None
    mock_ipv4_dns.return_value = ipv4_records("192.0.2.10")
    assert await async_ipv4_addresses(hass, "nvx.example.local") == {"192.0.2.10"}


async def test_dns_concurrency_is_bounded(hass, mock_ipv4_dns):
    active = peak = 0

    async def resolve(*args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return ipv4_records("192.0.2.10")

    mock_ipv4_dns.side_effect = resolve
    await asyncio.gather(
        *(
            async_ipv4_addresses(hass, f"nvx-{index}.example.local")
            for index in range(12)
        )
    )
    assert peak == 4


def registered_entry(
    hass, *, serial="synthetic-serial", model="DM-NVX-350", unique_id="original"
):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id=unique_id)
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, unique_id)},
        serial_number=serial,
        model=model,
    )
    return entry


async def test_authenticated_serial_matches_alternate_interface(hass):
    entry = registered_entry(hass)
    assert authenticated_entry(hass, SNAPSHOT.device) is entry


@pytest.mark.parametrize(
    "serial", [None, "", "unknown", "n/a", "none", "000000", "   "]
)
async def test_missing_or_placeholder_serial_is_not_identity(hass, serial):
    registered_entry(hass, serial=serial)
    assert (
        authenticated_entry(hass, replace(SNAPSHOT.device, serial_number=serial))
        is None
    )


async def test_serial_requires_matching_model_and_unambiguous_entry(hass):
    registered_entry(hass, model="DM-NVX-360")
    assert authenticated_entry(hass, SNAPSHOT.device) is None
    registered_entry(hass, unique_id="second")
    registered_entry(hass, unique_id="third")
    assert authenticated_entry(hass, SNAPSHOT.device) is None


async def test_exact_rest_id_takes_precedence(hass):
    entry = registered_entry(hass, unique_id=SNAPSHOT.device.device_id)
    registered_entry(hass, unique_id="second")
    assert authenticated_entry(hass, SNAPSHOT.device) is entry
