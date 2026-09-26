"""Discovery framing, scope, pacing and socket lifecycle tests; no network I/O."""

import asyncio
from ipaddress import IPv4Network
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.crestron_nvx import discovery as d


def response(
    hostname="living-room", description="DM-NVX-360 [v7.1.5259.00068 (Jan 02 2025)]"
):
    """Synthetic fixed-width fields, not a saved hardware packet."""
    return (
        b"\0" * 10
        + hostname.encode().ljust(256, b"\0")
        + description.encode().ljust(128, b"\0")
    )


def test_parse_metadata():
    device = d.parse_response(response(), "192.0.2.10")
    assert device == d.DiscoveredDevice(
        "192.0.2.10", "living-room", "DM-NVX-360", "7.1.5259.00068", "Jan 02 2025"
    )
    assert device.label == "living-room — DM-NVX-360 (192.0.2.10)"


@pytest.mark.parametrize("model", ["DM-NVX-350", "DM-NVX-360", "DM-NVX-E30"])
def test_optional_metadata(model):
    device = d.parse_response(response(description=model), "192.0.2.10")
    assert device.model == model
    assert device.firmware is None
    assert device.build_date is None


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        d.PROBE,
        response()[:270],
        response() + b"x" * 4096,
        response(hostname=""),
        response(hostname="bad\nname"),
        response(hostname="café"),
        response(description="DM-NVX-360\n" + "bad"),
        response(description="CP3 [v1.2.3]"),
        response(description="DM-NVX-UNKNOWN"),
    ],
)
def test_reject_bad_or_unsupported_packets(payload):
    assert d.parse_response(payload, "192.0.2.10") is None


@pytest.mark.parametrize("host", ["bad", "::1", "127.0.0.1", "224.0.0.1"])
def test_reject_invalid_source(host):
    assert d.parse_response(response(), host) is None


@pytest.mark.parametrize(
    "target",
    [
        "192.0.2.0/23",
        "::1",
        "example.local",
        "127.0.0.1",
        "0.0.0.0",
        "224.0.0.0/24",
        "255.255.255.255",
        "not a subnet",
    ],
)
def test_target_limits(target):
    with pytest.raises(ValueError):
        d.parse_target(target)


def test_target_normalization():
    assert d.parse_target("  ") is None
    assert d.parse_target("192.0.2.10") == IPv4Network("192.0.2.10/32")
    assert d.parse_target(" 192.0.2.5/24 ") == IPv4Network("192.0.2.0/24")


def test_unpadded_description_and_older_firmware():
    payload = response(description="DM-NVX-350 [v1.3707.00028]").rstrip(b"\0")
    device = d.parse_response(payload, "192.0.2.10")
    assert device.firmware == "1.3707.00028"
    assert device.build_date is None


def test_reply_scope_duplicates_and_capacity():
    devices = {}
    replies = d._Replies(IPv4Network("192.0.2.0/24"), {"192.0.2.1"}, devices)
    for host in ["192.0.2.1", "198.51.100.1"]:
        replies.datagram_received(response(), (host, 12345))
    replies.datagram_received(d.PROBE, ("192.0.2.2", 41794))
    assert not devices
    for port in [10000, 20000]:
        replies.datagram_received(response(), ("192.0.2.10", port))
    assert len(devices) == 1
    with patch.object(d, "MAX_TARGETS", 1):
        replies.datagram_received(response(), ("192.0.2.11", 10000))
    assert len(devices) == 1


@pytest.fixture
def adapter():
    return {
        "enabled": True,
        "name": "eth0",
        "default": True,
        "auto": True,
        "index": 1,
        "ipv4": [{"address": "192.0.2.1", "network_prefix": 24}],
        "ipv6": [],
    }


@pytest.fixture
async def sockets(adapter):
    transports = []

    async def open_socket(factory, **kwargs):
        transport = MagicMock()
        transports.append(transport)
        protocol = factory()
        protocol.datagram_received(response(), ("192.0.2.10", 54321))
        return transport, protocol

    with (
        patch.object(
            d.network, "async_get_adapters", AsyncMock(return_value=[adapter])
        ),
        patch.object(
            d.network, "async_get_source_ip", AsyncMock(return_value="192.0.2.1")
        ),
        patch.object(
            asyncio.get_running_loop(),
            "create_datagram_endpoint",
            side_effect=open_socket,
        ) as create,
        patch.object(d, "_REPLY_TIMEOUT", 0),
        patch.object(d, "_SEND_INTERVAL", 0),
    ):
        yield create, transports


async def test_broadcast(hass, sockets):
    create, transports = sockets
    devices = await d.async_discover(hass)
    assert len(devices) == 1
    assert create.call_args.kwargs["local_addr"] == ("192.0.2.1", 41794)
    assert create.call_args.kwargs["allow_broadcast"] is True
    assert len(d.PROBE) == 266
    assert d.PROBE[:10] == bytes.fromhex("14000000010400030000")
    assert transports[0].sendto.call_count == 2
    transports[0].sendto.assert_called_with(d.PROBE, ("192.0.2.255", 41794))
    transports[0].close.assert_called_once()


async def test_unicast_subnet_excludes_broadcast_network_and_self(hass, sockets):
    _, transports = sockets
    await d.async_discover(hass, IPv4Network("192.0.2.0/30"))
    assert transports[0].sendto.call_count == 2
    transports[0].sendto.assert_called_with(d.PROBE, ("192.0.2.2", 41794))


async def test_remote_unicast_uses_selected_source(hass, sockets):
    _, transports = sockets
    assert not await d.async_discover(hass, IPv4Network("198.51.100.10/32"))
    d.network.async_get_source_ip.assert_awaited_with(hass, "198.51.100.10")
    transports[0].sendto.assert_called_with(d.PROBE, ("198.51.100.10", 41794))


@pytest.mark.parametrize(
    "case", ["disabled", "ipv6", "loopback", "point_to_point", "self", "wrong_source"]
)
async def test_no_suitable_interface(hass, sockets, adapter, case):
    target = None
    if case == "disabled":
        adapter["enabled"] = False
    elif case == "ipv6":
        adapter["ipv4"] = []
    elif case == "loopback":
        adapter["ipv4"][0]["address"] = "127.0.0.1"
    elif case == "point_to_point":
        adapter["ipv4"][0]["network_prefix"] = 32
    elif case == "self":
        target = IPv4Network("192.0.2.1/32")
    else:
        target = IPv4Network("198.51.100.10/32")
        d.network.async_get_source_ip.return_value = "198.51.100.1"
    with pytest.raises(d.DiscoveryError):
        await d.async_discover(hass, target)


async def test_bind_failure_releases_lock(hass, sockets):
    create, _ = sockets
    create.side_effect = OSError("port in use")
    with pytest.raises(d.DiscoveryError):
        await d.async_discover(hass)
    assert not hass.data[d._LOCK_KEY].locked()


async def test_partial_bind_failure_closes_existing_socket(hass, sockets, adapter):
    create, transports = sockets
    original = create.side_effect
    adapter["ipv4"].append({"address": "192.0.2.2", "network_prefix": 24})

    async def fail_second(*args, **kwargs):
        if transports:
            raise OSError("port in use")
        return await original(*args, **kwargs)

    create.side_effect = fail_second
    with pytest.raises(d.DiscoveryError):
        await d.async_discover(hass)
    transports[0].close.assert_called_once()


async def test_cancel_closes_socket_and_releases_lock(hass, sockets):
    _, transports = sockets
    with (
        patch.object(d.asyncio, "sleep", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await d.async_discover(hass)
    transports[0].close.assert_called_once()
    assert not hass.data[d._LOCK_KEY].locked()


async def test_busy_does_not_open_second_socket(hass, sockets):
    create, _ = sockets
    lock = hass.data[d._LOCK_KEY] = asyncio.Lock()
    async with lock:
        with pytest.raises(d.DiscoveryBusyError):
            await d.async_discover(hass)
    create.assert_not_called()


async def test_non_ui_caller_cannot_bypass_target_limit(hass, sockets):
    with pytest.raises(ValueError):
        await d.async_discover(hass, IPv4Network("192.0.0.0/16"))
