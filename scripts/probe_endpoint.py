"""Safely probe the currently implemented read-only DM NVX API surface."""

import argparse
import asyncio
import json
from collections.abc import Mapping
from getpass import getpass
from typing import Any, Final

from aiohttp import ClientSession
from crestron_nvx import NvxApiError, NvxClient, NvxReadPath

_PUBLIC_SCHEMA_KEYS: Final = frozenset(
    {
        "ActiveAudioSource",
        "ActiveBitrate",
        "ActiveVideoSource",
        "AudioMode",
        "AudioSource",
        "AudioVideoInputOutput",
        "AutoInitiationMode",
        "AutoInputRoutingEnabled",
        "Bitrate",
        "CodecReady",
        "Device",
        "DeviceId",
        "DeviceInfo",
        "DeviceMode",
        "DeviceReady",
        "DeviceSpecific",
        "DeviceVersion",
        "FramesPerSecond",
        "HdcpState",
        "Hdmi",
        "HorizontalResolution",
        "Inputs",
        "IsFrontPanelLockoutEnabled",
        "IsSinkConnected",
        "IsSyncDetected",
        "LedsEnabled",
        "MacAddress",
        "Manufacturer",
        "Model",
        "MotionDetected",
        "Name",
        "NaxActiveAudioSource",
        "NaxAudioSource",
        "NaxAudioSourceOptionsName",
        "NaxAudioSourceOptionsVersion",
        "Outputs",
        "Ports",
        "Preview",
        "IsPreviewOutputEnabled",
        "HostPreviewImage",
        "LocalPreview",
        "LocalPreviewPath",
        "RelativePath",
        "IPv4Path",
        "FQDNPath",
        "ImageList",
        "IsImageAvailable",
        "Size",
        "Width",
        "Height",
        "RebootReason",
        "SerialNumber",
        "ShowSetupInformationOnOsd",
        "Status",
        "StreamReceive",
        "Streams",
        "StreamTransmit",
        "Transmitting",
        "UUID",
        "Uuid",
        "Version",
        "VerticalResolution",
        "VideoSource",
        "VideoWallMode",
    }
)


def _shape(value: Any) -> Any:
    """Replace values with their types while preserving response shape."""
    if isinstance(value, Mapping):
        shaped: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            text_key = str(key)
            # Unknown keys can be user-assigned stream, room, or endpoint names.
            # Preserve only the public schema vocabulary reviewed in this tool.
            safe_key = text_key if text_key in _PUBLIC_SCHEMA_KEYS else "<entry>"
            shaped[safe_key] = _shape(item)
        return shaped
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


async def _async_probe(
    host: str, username: str, verify_ssl: bool, preview: bool = False
) -> None:
    """Read and print a privacy-minimized endpoint summary."""
    password = getpass("DM NVX password: ")
    async with ClientSession() as session:
        client = NvxClient(
            session,
            host,
            username,
            password,
            verify_ssl=verify_ssl,
        )
        snapshot = await client.async_get_snapshot()
        object_shapes: dict[str, Any] = {}
        for path in NvxReadPath:
            try:
                payload = await client.async_get_read_only_object(path)
            except NvxApiError as err:
                object_shapes[path.name] = {"error": type(err).__name__}
            else:
                object_shapes[path.name] = _shape(payload)
        preview_result: dict[str, Any] = {}
        if preview:
            try:
                info = await client.async_get_preview_info()
                preview_result = {
                    "supported": info.supported,
                    "enabled": info.enabled,
                    "local_image_available": info.path is not None,
                }
                if info.path:
                    image = await client.async_get_preview()
                    preview_result.update(
                        {
                            "http_status": 200,
                            "content_type": image.content_type,
                            "bytes": len(image.content),
                            "width": image.width,
                            "height": image.height,
                            "authentication": "authenticated session; anonymous access not tested",
                        }
                    )
            except NvxApiError as err:
                preview_result["error"] = type(err).__name__
    print(
        json.dumps(
            {
                "model": snapshot.device.model,
                "firmware_version": snapshot.device.firmware_version,
                "device_specific_shape": _shape(snapshot.raw_device_specific),
                "documented_object_shapes": object_shapes,
                "preview_check": preview_result,
            },
            indent=2,
            sort_keys=True,
        )
    )


def main() -> None:
    """Run the read-only endpoint probe."""
    parser = argparse.ArgumentParser(
        description="Read identity and DeviceSpecific shape from one DM NVX endpoint."
    )
    parser.add_argument("host", help="Endpoint host name or IP address")
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Fetch a preview in memory and report metadata only",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify the endpoint TLS certificate",
    )
    arguments = parser.parse_args()
    try:
        asyncio.run(
            _async_probe(
                arguments.host,
                arguments.username,
                arguments.verify_ssl,
                arguments.preview,
            )
        )
    except NvxApiError as err:
        parser.exit(1, f"Probe failed: {err}\n")


if __name__ == "__main__":
    main()
