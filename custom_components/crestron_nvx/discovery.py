"""Bounded, read-only Crestron UDP discovery, independent of config-flow UI.

See docs/DISCOVERY.md for packet provenance and the observed reply layout.
Discovery metadata is unauthenticated and must never establish device identity.
"""

import asyncio
import re
import socket
from dataclasses import dataclass
from functools import partial
from ipaddress import IPv4Address, IPv4Interface, IPv4Network

from homeassistant.components import network
from homeassistant.core import HomeAssistant

from .const import SUPPORTED_MODELS

DISCOVERY_PORT = 41794
MAX_TARGETS = 256
PROBE = bytes.fromhex("14000000010400030000") + b"ha-nvx-discovery".ljust(256, b"\0")
_LOCK_KEY = "crestron_nvx_discovery_lock"
_REPLY_TIMEOUT = 3.0
_SEND_INTERVAL = 0.01
_MODEL = re.compile(r"^(DM-NVX-[A-Za-z0-9-]+)(?:\s|$)")
_FIRMWARE = re.compile(r"\[v(\d+(?:\.\d+)+)", re.IGNORECASE)
_BUILD_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}\b"
)


class DiscoveryError(Exception):
    """Discovery could not open or use a local interface."""


class DiscoveryBusyError(DiscoveryError):
    """A discovery session already owns the reply port."""


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A candidate endpoint; host is the packet's source IPv4 address."""

    host: str
    hostname: str
    model: str
    firmware: str | None = None
    build_date: str | None = None

    @property
    def label(self) -> str:
        """Differentiate even endpoints with duplicate hostnames."""
        return f"{self.hostname} — {self.model} ({self.host})"


def _usable_address(address: IPv4Address) -> bool:
    return not (
        address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or address.is_reserved
    )


def parse_target(value: str) -> IPv4Network | None:
    """Accept a single IPv4 address or at most a /24; blank means local broadcast."""
    if not value.strip():
        return None
    target = IPv4Network(value.strip(), strict=False)
    if target.num_addresses > MAX_TARGETS or not all(
        _usable_address(address)
        for address in (target.network_address, target.broadcast_address)
    ):
        raise ValueError("Use a unicast IPv4 address or a subnet of /24 or smaller")
    return target


def parse_response(data: bytes, host: str) -> DiscoveredDevice | None:
    """Read the observed fixed fields; tolerate missing optional version details."""
    if not 267 <= len(data) <= 4096:
        return None
    try:
        if not _usable_address(IPv4Address(host)):
            return None
        hostname = data[10:266].split(b"\0", 1)[0].decode("ascii").strip()
        description = data[266:394].split(b"\0", 1)[0].decode("ascii").strip()
    except ValueError, UnicodeDecodeError:
        return None
    model_match = _MODEL.match(description)
    if (
        not hostname
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}", hostname)
        or not description.isprintable()
        or not model_match
        or (model := model_match[1]) not in SUPPORTED_MODELS
    ):
        return None
    firmware = _FIRMWARE.search(description)
    build_date = _BUILD_DATE.search(description)
    return DiscoveredDevice(
        host=host,
        hostname=hostname,
        model=model,
        firmware=firmware[1] if firmware else None,
        build_date=build_date[0] if build_date else None,
    )


class _Replies(asyncio.DatagramProtocol):
    """Collect only bounded replies from the requested network."""

    def __init__(
        self,
        scope: IPv4Network,
        local_hosts: set[str],
        devices: dict[str, DiscoveredDevice],
    ) -> None:
        self.scope = scope
        self.local_hosts = local_hosts
        self.devices = devices

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        host = addr[0]
        if host in self.local_hosts or len(self.devices) >= MAX_TARGETS:
            return
        if IPv4Address(host) not in self.scope:
            return
        if device := parse_response(data, host):
            self.devices[host] = device


async def async_discover(
    hass: HomeAssistant, target: IPv4Network | None = None
) -> list[DiscoveredDevice]:
    """Search enabled HA interfaces, or explicitly supplied routed IPv4 targets.

    One socket per source address receives on 41794: hardware ignores the
    request's source port. No port sharing or persistent listener is installed.
    """
    if target is not None:
        parse_target(str(target))  # Enforce limits even for non-UI callers.
    lock: asyncio.Lock = hass.data.setdefault(_LOCK_KEY, asyncio.Lock())
    if lock.locked():
        raise DiscoveryBusyError
    async with lock:
        adapters = await network.async_get_adapters(hass)
        interfaces = {
            IPv4Interface(f"{info['address']}/{info['network_prefix']}")
            for adapter in adapters
            if adapter["enabled"]
            for info in adapter["ipv4"]
            if _usable_address(IPv4Address(info["address"]))
        }
        local_hosts = {str(interface.ip) for interface in interfaces}
        plans: list[tuple[str, IPv4Network, list[str]]] = []
        if target is not None:
            destinations = [
                str(ip) for ip in target.hosts() if str(ip) not in local_hosts
            ]
            if destinations:
                source = await network.async_get_source_ip(hass, destinations[0])
                if source in local_hosts:
                    plans.append((source, target, destinations))
        else:
            plans = [
                (str(item.ip), item.network, [str(item.network.broadcast_address)])
                for item in sorted(interfaces, key=lambda item: int(item.ip))
                if item.network.prefixlen < 31
            ]
        if not plans:
            raise DiscoveryError("No enabled IPv4 interface for discovery")
        devices: dict[str, DiscoveredDevice] = {}
        transports: list[tuple[asyncio.DatagramTransport, list[str]]] = []
        loop = asyncio.get_running_loop()
        try:
            for source, scope, destinations in plans:
                transport, _ = await loop.create_datagram_endpoint(
                    partial(_Replies, scope, local_hosts, devices),
                    local_addr=(source, DISCOVERY_PORT),
                    family=socket.AF_INET,
                    allow_broadcast=True,
                )
                transports.append((transport, destinations))
            for _ in range(2):
                for transport, destinations in transports:
                    for destination in destinations:
                        transport.sendto(PROBE, (destination, DISCOVERY_PORT))
                        await asyncio.sleep(_SEND_INTERVAL)
            await asyncio.sleep(_REPLY_TIMEOUT)
        except OSError as err:
            raise DiscoveryError("Unable to use UDP discovery port") from err
        finally:
            for transport, _ in transports:
                transport.close()
            # Datagram transports release their socket in a scheduled callback.
            # Allow that callback to run before another scan acquires the lock.
            await asyncio.sleep(0)
        return sorted(devices.values(), key=lambda device: device.label.casefold())
