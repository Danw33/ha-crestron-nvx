"""Test configuration for Crestron DM NVX."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from crestron_nvx import (
    NvxAvPort,
    NvxDeviceInfo,
    NvxPreviewInfo,
    NvxSnapshot,
    NvxStream,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.crestron_nvx.const import CONF_VERIFY_SSL, DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

DEVICE_ID = "synthetic-device-id"
HOST = "nvx.example.local"
MOCK_DATA = {
    CONF_HOST: HOST,
    CONF_USERNAME: "test-user",
    CONF_PASSWORD: "test-password",
    CONF_VERIFY_SSL: False,
}
SNAPSHOT = NvxSnapshot(
    device=NvxDeviceInfo(
        device_id=DEVICE_ID,
        name="Synthetic NVX",
        model="DM-NVX-350",
        serial_number="synthetic-serial",
        firmware_version="7.1.0",
        mac_address="00:00:00:00:00:00",
        reboot_reason="poweron",
    ),
    device_mode="Receiver",
    device_ready=True,
    active_audio_source="PrimaryStreamAudio",
    active_video_source="Stream",
    audio_mode="DAC",
    audio_source="AudioFollowsVideo",
    video_source="Stream",
    nax_active_audio_source="PrimaryAudio",
    nax_audio_source="PrimaryAudio",
    auto_initiation_mode=False,
    auto_input_routing_enabled=True,
    front_panel_lockout_enabled=False,
    leds_enabled=True,
    show_setup_information_on_osd=False,
    av_ports=(
        NvxAvPort(
            port_id="input-port",
            name="HDMI input",
            direction="input",
            sync_detected=True,
            hdcp_state="HDCP2",
            horizontal_resolution=1920,
            vertical_resolution=1080,
            frames_per_second=60,
        ),
        NvxAvPort(
            port_id="output-port",
            name="HDMI output",
            direction="output",
            sink_connected=True,
            transmitting=True,
            horizontal_resolution=1920,
            vertical_resolution=1080,
            frames_per_second=60,
        ),
    ),
    receive_streams=(
        NvxStream(
            stream_id="receive_0",
            direction="receive",
            status="Started",
            codec_ready=True,
            bitrate_mbps=800,
            horizontal_resolution=1920,
            vertical_resolution=1080,
            frames_per_second=60,
        ),
    ),
    transmit_streams=(
        NvxStream(
            stream_id="transmit-id",
            direction="transmit",
            status="Started",
            codec_ready=True,
            bitrate_mbps=750,
            horizontal_resolution=1920,
            vertical_resolution=1080,
            frames_per_second=60,
        ),
    ),
    raw_device_specific={"DeviceMode": "Receiver", "DeviceReady": True},
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable custom integrations for every test."""


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a synthetic config entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=SNAPSHOT.device.name,
        unique_id=DEVICE_ID,
        data=MOCK_DATA,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_client() -> Generator[AsyncMock]:
    """Mock all endpoint I/O."""

    with (
        patch(
            "crestron_nvx.NvxClient.async_get_preview_info",
            new=AsyncMock(return_value=NvxPreviewInfo()),
        ),
        patch(
            "custom_components.crestron_nvx.NvxClient.async_get_snapshot",
            new=AsyncMock(return_value=SNAPSHOT),
        ) as client,
    ):
        yield client
