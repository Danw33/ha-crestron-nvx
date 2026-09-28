"""Separate address hints from authenticated physical-device identity."""

import asyncio
import socket
from ipaddress import ip_address

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from crestron_nvx import NvxDeviceInfo

from .const import DOMAIN

_DNS_TIMEOUT = 2.0
_DNS_LIMIT_KEY = f"{DOMAIN}_identity_dns_limit"


async def async_ipv4_addresses(hass: HomeAssistant, host: str) -> set[str]:
    """Resolve only user-configured hosts, never names supplied by UDP replies.

    Address matches suppress setup suggestions, not establish physical identity.
    No credentials are sent, and failed DNS leaves discovery usable.
    """
    host = host.strip().lower().rstrip(".")
    try:
        address = ip_address(host)
    except ValueError:
        pass
    else:
        return {str(address)} if address.version == 4 else set()

    limit: asyncio.Semaphore = hass.data.setdefault(
        _DNS_LIMIT_KEY, asyncio.Semaphore(4)
    )
    try:
        async with asyncio.timeout(_DNS_TIMEOUT), limit:
            results = await asyncio.get_running_loop().getaddrinfo(
                host, None, family=socket.AF_INET, type=socket.SOCK_STREAM
            )
    except OSError, TimeoutError:
        return set()
    return {str(result[4][0]) for result in results}


async def async_configured_addresses(hass: HomeAssistant) -> set[str]:
    """Return every current IPv4 address of configured endpoints, not titles."""
    hosts = {
        host
        for entry in hass.config_entries.async_entries(DOMAIN)
        if isinstance(host := entry.data.get(CONF_HOST), str) and host.strip()
    }
    addresses = await asyncio.gather(
        *(async_ipv4_addresses(hass, host) for host in hosts)
    )
    return set().union(*addresses)


def authenticated_entry(
    hass: HomeAssistant, device: NvxDeviceInfo
) -> ConfigEntry | None:
    """Match REST identity, including a serial when an interface ID differs.

    Registry serial numbers originate from authenticated REST snapshots, not
    labels, DNS, UDP metadata or an apparent MAC suffix in a hostname.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        if entry.unique_id == device.device_id:
            return entry
    serial = device.serial_number
    if (
        not serial
        or serial.casefold() in {"unknown", "none", "n/a"}
        or not serial.strip("0 -")
    ):
        return None
    registry = dr.async_get(hass)
    matches = [
        entry
        for entry in entries
        if entry.unique_id
        and any(
            registered.serial_number == serial and registered.model == device.model
            for registered in dr.async_entries_for_config_entry(
                registry, entry.entry_id
            )
        )
    ]
    return matches[0] if len(matches) == 1 else None
