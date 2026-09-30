"""HA option IDs are translatable while device commands retain API casing."""

import json
import re
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from crestron_nvx import NvxAvPort

from custom_components.crestron_nvx.select import (
    AUDIO_SOURCE_TO_API,
    VIDEO_SOURCE_TO_API,
    NvxAudioSourceSelect,
    NvxVideoSourceSelect,
)

from .conftest import DEVICE_ID, SNAPSHOT
from .test_switch import coordinator


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json"])
def test_option_translation_keys(filename):
    path = Path(__file__).parents[1] / "custom_components/crestron_nvx" / filename
    selects = json.loads(path.read_text())["entity"]["select"]
    for source, mapping in (
        ("video_source", VIDEO_SOURCE_TO_API),
        ("audio_source", AUDIO_SOURCE_TO_API),
    ):
        assert set(selects[source]["state"]) == set(mapping)
        assert all(re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", key) for key in mapping)


@pytest.mark.parametrize(
    ("source", "entity_type", "option", "api_value"),
    [
        (source, entity_type, option, api_value)
        for source, entity_type, mapping in (
            ("video_source", NvxVideoSourceSelect, VIDEO_SOURCE_TO_API),
            ("audio_source", NvxAudioSourceSelect, AUDIO_SOURCE_TO_API),
        )
        for option, api_value in mapping.items()
    ],
)
async def test_every_option_roundtrips(
    hass, mock_config_entry, source, entity_type, option, api_value
):
    snapshot = replace(
        SNAPSHOT,
        device=replace(SNAPSHOT.device, model="DM-NVX-350"),
        device_mode="Receiver",
        audio_mode="Insert",
        auto_input_routing_enabled=False,
        av_ports=tuple(
            NvxAvPort(f"input_slot{index}_hdmi_0", f"INPUT {index + 1}", "input")
            for index in range(2)
        ),
        **{source: api_value},
    )
    coord = coordinator(hass, mock_config_entry)
    coord.async_set_updated_data(snapshot)
    command = AsyncMock(return_value=snapshot)
    setattr(coord.client, f"async_set_{source}", command)
    entity = entity_type(coord)
    assert option in entity.options
    assert entity.current_option == option
    await entity.async_select_option(option)
    command.assert_awaited_once_with(api_value, expected_device_id=DEVICE_ID)
