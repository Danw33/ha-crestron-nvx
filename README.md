# Crestron DM NVX for Home Assistant

[![Install via Home Assistant Community Store (HACS)](https://img.shields.io/badge/HACS-Install-blue?logo=homeassistantcommunitystore&label=HACS&color=%2341BDF5&link=https%3A%2F%2Fmy.home-assistant.io%2Fredirect%2Fhacs_repository%2F%3Fowner%3DDanw33%26repository%3Dha-crestron-nvx%26category%3Dintegration)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Danw33&repository=ha-crestron-nvx&category=integration)
[![CI](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml)
[![Home Assistant validation](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

An early-stage custom integration for direct, local monitoring of Crestron
DM NVX AV-over-IP endpoints. Controls are selected from the capabilities reported
by each endpoint, not an exact-model allowlist. Live validation currently covers
DM-NVX-350/360 on firmware 7.1 and DM-NVX-E30 on firmware 6.0.

> [!IMPORTANT]
> This is an independent, unofficial community integration. It is not
> affiliated with, endorsed by, sponsored by, or supported by Crestron
> Electronics, Inc. Crestron, DM NVX, and related names and marks are
> trademarks of their respective owners. Their use here identifies compatible
> products only. Do not contact Crestron support for help with this integration.

This integration is maintained by its community contributors, not by Home
Assistant, HACS, or Crestron. Device APIs and firmware behaviour can change.
Compatibility with future firmware or every DM NVX model is not guaranteed.

## API provenance

Monitoring, previews and controls communicate through Crestron's **publicly accessible
and publicly documented DM NVX REST API**. The optional UDP discovery probe
uses public research and hardware interoperability observations. No confidential or
private information is used.

The authoritative external references are Crestron's public:

- [DM NVX REST API reference](https://sdkcon78221.crestron.com/sdk/DM_NVX_REST_API/Content/Topics/API-Reference.htm)
- [DM NVX API authentication guide](https://sdkcon78221.crestron.com/sdk/DM_NVX_REST_API/Content/Topics/Authentication.htm)

Those references describe HTTPS authentication, GET/POST methods, object
paths, property types, and model-specific applicability. This repository does
not copy or redistribute Crestron manuals, schemas, examples, firmware, or
other proprietary material. Public documentation does not imply that Crestron
endorses this project or guarantees continued API compatibility.

See [API provenance and clean-source policy](docs/API_PROVENANCE.md) for the
project's documentation, hardware-observation, and fixture rules.

## Project status

Version 0.7.0 adds opt-in local controls to the existing monitoring integration.
Immediate discovery cards, configured-hostname duplicate filtering and consistent
built-in port labels were validated with 0.6.0. Unknown alternate-interface
matching remains unverified.

Setup and monitoring have been observed on firmware 7.1 DM-NVX-350/360 and
firmware 6.0 DM-NVX-E30 endpoints. Preview display, updates, HA Media and remote
iOS viewing were validated on the 360; preview operation was also reported on
the E30, and preview entities were observed on both configured 350s.
It currently:

- configures one physical endpoint per Home Assistant config entry;
- authenticates locally over HTTPS using Home Assistant's shared async session;
- reads the public `DeviceInfo`, `DeviceSpecific`, `AudioVideoInputOutput`,
  `StreamReceive`, and `StreamTransmit` API objects;
- creates stable device/entity registry identifiers from the endpoint device ID;
- exposes device/source status, input sync, output connection/transmission,
  detected resolutions, stream status, codec readiness, and active bitrate when
  those fields are present;
- provides redacted diagnostics, reauthentication, reconfiguration, and clean
  config-entry unloading;
- exposes a preview image only when the API reports preview capability.

Version **0.7.0** adds opt-in controls using `crestron-nvx==0.4.0`: device LEDs,
video/audio source selection, reboot, primary receiver routing and primary
stream start/stop. All controls are disabled by default; setup and monitoring
do not change device configuration. Device mode control is not implemented.

LED off/on has been physically tested (the tested model/firmware combinations
remain to be recorded). Routing was tested on a receiving 350 with 350 and E30
transmitters; a subsequent E30 test-pattern playback issue remains unresolved.
Reboot has been physically tested. Successful source-selection writes and stream
start/stop still need hardware validation. Treat those controls as experimental and test
on an idle endpoint before using them in automations.

### Optional Receiver stream select

Enable **Receiver stream** on a capability-compatible DM NVX receiver. Choices
are primary streams advertised by transmitters already configured and available
in HA with the required capabilities. Labels use the HA device's custom name, falling back to
the integration entry title, plus device identity to distinguish duplicate names.
Adding a transmitter to HA does not route it automatically.

Only primary receive slot 0's URL is changed. The receiver must already use
**Multicast via RTSP** and must not be processing another stream command. To
view the result, ensure the receiver is using the Stream video source and that
stream initiation and credentials are already configured appropriately. This
control does not change video/audio source, credentials, automatic input routing,
device mode or stream start/stop settings. Routing can interrupt current viewing.

Unknown or external routes display Unknown; duplicate advertised URLs are not
guessed. No eligible transmitters means Unavailable. Choices refresh with device
updates and entry setup/unload. After a device mode change, reload its integration
entry if the receiver control was not originally created. IPv6, secondary stream
slots and arbitrary URL entry are outside this checkpoint.

Selecting a transmitter performs a fresh identity/capability check, followed by
an identity-checked receiver write and URL readback. An unchanged route is a
no-op. Readback confirms configuration, not playback. If an operation fails,
inspect the receiver before retrying; no write is automatically replayed.
Dan has verified routing on a receiving 350 between transmitting 350 and E30
devices using the standalone checkpoint ZIP. Other routing combinations remain
to be validated. The implementation uses the
public [StreamReceive API](https://sdkcon78221.crestron.com/sdk/DM_NVX_REST_API/Content/Topics/Objects/StreamReceive.htm).

### Optional primary stream buttons

Enable **Start receiving** / **Stop receiving** on a receiver, or **Start
transmitting** / **Stop transmitting** on a transmitter. These operational
buttons are disabled by default and affect only primary stream slot 0. The
Eligibility follows the reported receiver or transmitter mode and addressable
stream fields, rather than a model list. Opposite-direction telemetry is never treated as a capability.
After changing device mode externally, reload the entry to register its new
buttons; existing buttons never silently switch direction.

**Stopping a transmitter can interrupt every receiver using its stream.** Each
press checks identity, mode and that the stream is not busy, sends `Start: true`
or `Stop: true` once, and verifies the reported stream status. Starting reception
requires an existing valid RTSP URL. No URL, credentials, audio/video source,
automatic initiation or other-slot settings are changed. Setup, enabling,
reload and restart never press a button or restore a previous desired state.

Reported status confirms the device's response, not successful playback. The
buttons are not a switch inferred from `Start`/`Stop` command flags, which may
not reflect stream status. Automatic initiation or another controller can change
the state again. If an outcome is uncertain, inspect the stream before retrying;
commands are never automatically replayed. Hardware start/stop validation is
pending. See the public [receive](https://sdkcon78221.crestron.com/sdk/DM_NVX_REST_API/Content/Topics/Objects/StreamReceive.htm)
and [transmit](https://sdkcon78221.crestron.com/sdk/DM_NVX_REST_API/Content/Topics/Objects/StreamTransmit.htm) API references.

### Optional Reboot button

**Reboot** is a disabled-by-default diagnostic entity on supported models.
Enabling the entity, starting HA and reloading the integration do not reboot
anything; only pressing it sends a request. The action verifies endpoint
identity, posts `DeviceOperations.Reboot` once and checks an acknowledgement
when one arrives. It does not send factory restore or reset commands.

Video and audio will be interrupted during a real reboot. The device may close
its connection before acknowledging the command; if HA reports an uncertain
outcome, check whether it is already restarting before pressing again. The
button does not wait for the endpoint to return. Reboot has been physically tested;
this does not establish validation for every model or firmware version.

### Optional Video source select

Enable **Video source** in entity settings to choose a supported configured
source. Options use the library's observed HDMI input slots and current mode;
Input 2 requires a mapped second input, and Stream is offered only in receiver mode.
Unknown capabilities are not guessed. The configured selection may differ from
the existing **Active video source** sensor. Enabling or reloading never writes.

For automations, video options are `none`, `input_1`, `input_2` and `stream`
(subject to device capabilities). HA displays translated labels; the integration
maps these IDs to the device's case-sensitive API values.

Disable automatic input routing in the device web UI before changing sources.
HA will not disable it for you and refuses changes if its state is enabled or
unknown. Selecting the current supported source is a no-op. Only VideoSource
is written, with identity preflight and readback; audio, routing automation and
stream addresses are not written. Video changes can interrupt viewing and affect
audio configured to follow video. Hardware write validation is still pending.

### Optional Audio source select

Enable **Audio source** in entity settings to choose a supported configured
source. Options depend on reported mode, observed HDMI inputs and analog
Insert/Extract mode. Receivers reporting receive streams may offer primary
stream audio. Secondary stream and NAX audio source choices are deferred until
their device-specific API values are validated. The select represents the
configured source; **Active audio source** remains read-only telemetry.

Audio option IDs for automations are `audio_follows_video`, `input_1`, `input_2`,
`analog_audio` and `primary_stream_audio`, subject to device capabilities.
If testing an earlier unreleased build, update any automations using the old
PascalCase option values. Entity unique IDs and display labels are unchanged.

Manual changes require automatic input routing to be explicitly off. Only
`AudioSource` is written, with a fresh device identity and capability check,
one POST, and configured-state readback. The control does not alter analog
mode, video routing or NAX configuration. Changing it can interrupt audio.
Hardware write validation remains pending.

### Optional Device LEDs switch

When the endpoint reports LED state, a disabled-by-default configuration switch
is registered. Enable **Device LEDs** in entity settings to use it. Enabling it,
restarting or reloading HA does not change LEDs; only an explicit switch action
writes. The existing LED binary sensor remains unchanged. Disabled-by-default
is a UI choice, not an access-control boundary.

Actions verify the endpoint identity and read back state. After a failed command,
check the device state before retrying: it may already have applied. A read-only
account may monitor successfully but be denied control. No command is automatically
replayed or followed by reboot/reset. TLS verification remains recommended;
without it, an on-path impersonator can also falsify identity responses.

## Roadmap

1. Complete Phase 1 status coverage using sanitized observations from each
   target model, including stream, input-sync, and output-sync state.
2. Complete preview lifecycle, resilience and remaining discovery edge-case checks.
3. Design separately reviewed, explicitly guarded control entities/actions.
4. Add stream-to-endpoint selection with a Home Assistant-native UX.
5. Validate device-wide discovery identity across unknown interfaces; consider
   IPv6 discovery/address matching separately after the IPv4 implementation.

The design aims to remain compatible with Home Assistant's Gold/Platinum
architecture expectations, but this custom integration does **not** claim an
official Home Assistant quality rating.

Protocol communication and typed response models are provided by the
standalone [crestron-nvx](https://github.com/Danw33/py-crestron-nvx)
library. Home Assistant installs the exact version pinned in the integration
manifest, giving fresh manual and HACS installations a reproducible dependency.

## Installation

### Manual installation

Copy `custom_components/crestron_nvx` into the `custom_components` directory in
your Home Assistant configuration, restart Home Assistant, then add
**Crestron DM NVX** from **Settings → Devices & services → Add integration**.

Version 0.7.0 requires `crestron-nvx==0.4.0` to be available on PyPI. When
upgrading from a private test ZIP, replace the complete integration directory
rather than merging files, so the private `_client` directory is removed.
Back up your existing installation first; keep your HA config entries.

For testing before library publication, `scripts/build_local_zip.py` accepts
`--library /path/to/py-crestron-nvx`, `--version 0.7.0b3` and `--output /path/to/test.zip`.
It bundles the client only inside the archive and leaves source imports and
the release manifest unchanged. These private builds are not release assets.

### HACS

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Danw33&repository=ha-crestron-nvx&category=integration)

Requires HACS to be installed in your Home Assistant instance.

Add `Danw33/ha-crestron-nvx` as a custom HACS repository of type Integration,
download, restart Home Assistant, and add it through Devices & services.

## Configuration

Choose **Search for devices** or **Enter host manually**. Search with an empty
target for local broadcast, or enter an IPv4 address/subnet (up to /24) for
devices on another routed VLAN. Select a result by hostname, model and IP,
then enter credentials to verify and add it. Searches run only when requested;
they do not automatically add devices. Results also appear in **Discovered**
as soon as the scan finishes, even if you close the search dialog without
adding a device. These temporary cards let you add the remaining devices
without scanning again; successful setup removes the matching card.
Routed discovery requires working UDP return traffic; routing alone does not
forward broadcast discovery to another VLAN.

Configured hostnames are matched through all their current IPv4 DNS answers,
not device display names. Authenticated duplicate setup checks REST identity
and, when unambiguous, model/serial number, without replacing existing settings.
Unknown alternate interfaces can still appear before login: UDP discovery
does not provide an authenticated device-wide identity.

The connection form asks for:

- **Host name or IP address**: local management address of one endpoint;
- **Username and password**: a device account allowed to read the API, with
  appropriate write permissions if enabling controls;
- **Verify TLS certificate**: enable this when the certificate is trusted by
  the Home Assistant host. It defaults off because factory/local endpoints
  commonly use a self-signed certificate. When verification is disabled,
  Home Assistant cannot confirm that it is communicating with the intended
  endpoint; use that mode only on a trusted, isolated local network.

Credentials are stored in Home Assistant's config-entry storage. Use a
dedicated least-privilege account if the endpoint firmware supports one. Never
attach unredacted `.storage` files, network captures, cookies, or device dumps
to an issue.

## Data updates

One coordinator polls each endpoint every 30 seconds, and only while entities
are subscribed. A failed update makes normal entities unavailable. Home
Assistant logs a transition when the endpoint becomes unavailable and again
when it recovers. An authentication failure starts the reauthentication flow.

## Removal

Open **Settings → Devices & services**, select **Crestron DM NVX**, open the
endpoint menu, and choose **Delete**. The integration does not change the
endpoint during removal.

## Supported devices and functions

Discovery accepts DM NVX family model names, including D30, 351, 352, 363 and
unfamiliar variants. Authenticated library snapshots determine control support;
UDP metadata is not trusted to grant write capability. The additional models
are expected to be API-compatible, but have not been hardware-validated here.
Missing capabilities do not imply a broken device. Existing entities become
unavailable when their required observations disappear; no settings are written
to discover support. Some newly appearing controls require an integration reload.

| Model | Firmware | Compatibility evidence |
| --- | --- | --- |
| DM-NVX-350 | 2.0, 2.1, 3.1, 5.1, 5.2 | Hardware-captured payloads validated against the current parser; live HA testing pending |
| DM-NVX-350 | 6.0 | Supported; hardware-captured payloads validated; live HA testing pending |
| DM-NVX-350 | 7.0 | Hardware-captured payloads and preview metadata validated; live HA testing pending |
| DM-NVX-350 | 7.1 | Supported; payloads validated and live HA operation observed |
| DM-NVX-360 | 6.0 | Supported; hardware-captured payloads and preview metadata validated; live HA testing pending |
| DM-NVX-360 | 7.1 | Supported; payloads and live HA setup/preview operation validated |
| DM-NVX-E30 | 6.0 | Supported; live HA setup and preview validated |
| DM-NVX-E30 | 7.1 | Supported by shared-API assumption; direct validation pending |
| DM-NVX-D30 / 351 / 352 / 363 | API-compatible firmware | Capability-based; hardware validation pending |

Offline replay on 2026-09-29 successfully parsed all 19 supplied full-device
captures using `crestron-nvx` 0.3.0. No parser-blocking incompatibilities or
rejected populated telemetry types were found in the checked fields. The
firmware labels above use `DeviceInfo.DeviceVersion`, not update filenames.
They cover the specific captured builds, not every release in each family.
“Hardware-captured payloads validated” does not establish login/session behavior,
individual HTTP endpoint behavior, JPEG retrieval, full HA lifecycle or writes.
Older families remain compatibility candidates, not a new blanket minimum
supported firmware version. The earlier 1.3707.00028 probe is separate evidence.

The supplied 350 captures through 6.0 omit the Preview object; their monitoring
payloads still parse. The 360's 6.0 capture includes usable preview metadata.
Absence from a full-device capture alone does not prove that the dedicated
preview endpoint is unsupported. Preview availability remains capability-based.

Authentication and the Phase 1 response shape have been observed on two
DM-NVX-350 endpoints and one DM-NVX-360 running `7.1.5259.00068`, and one
DM-NVX-E30 running `6.0.4835.00027`. Capabilities are detected from returned
objects and fields because endpoints can omit inactive or inapplicable fields,
including endpoints of the same model on the same firmware. Older firmware may
be added to the supported range after validation on available hardware.

The initial manual 360 setup used a hostname and created 53 entities. Subsequent
HACS operation includes both 350s and the E30; counts vary with firmware,
capabilities, enabled diagnostics and retained legacy registry entries. Built-in
port labels now display as `Input 1` / `Output 1`; topology-confirmed `output0`
becomes `Output 1`. Custom labels and existing entity IDs are preserved.
Monitoring validation does not establish control compatibility; outstanding
control checks are listed above.

The linked public DM NVX REST API reference and authentication guide are
external, authoritative references. This repository does not reproduce vendor
manuals, schemas, examples, firmware, or other proprietary materials.

## Known limitations

- Initial field mapping is intentionally narrow. Not every supported
  model/firmware combination has been exercised on physical hardware.
- TLS is HTTPS-only in this initial implementation. Certificate verification is
  optional and disabled by default for compatibility with the self-signed
  certificates commonly installed on DM NVX endpoints. Without verification,
  an on-path device could impersonate the endpoint and receive its credentials;
  use this mode only on a trusted, isolated local network.
- Discovery is an on-demand IPv4 setup search; background discovery and
  automatic address updates from discovery are not implemented. Remote VLANs
  require an explicitly supplied target and working UDP return traffic.
- Unknown alternate interfaces cannot always be deduplicated before login;
  the UDP reply lacks a verified device-wide identity. IPv6 discovery is deferred.
- Preview availability is determined from capabilities, not an assumed
  firmware threshold.
- Long polling/WebSocket telemetry is deferred until polling behaviour is
  understood on the target firmware.
- All controls require explicit opt-in. Hardware validation varies by control
  and observed capabilities; see the control sections above. Device mode changes and secondary
  stream control are not implemented.

## Troubleshooting

- **Failed to connect**: confirm Home Assistant can route to TCP port 443 on the
  management interface and that the endpoint web interface opens locally.
- **Invalid authentication**: verify the account in the endpoint web interface,
  then use the integration's reauthentication flow. Repeated bad passwords may
  trigger endpoint security protections.
- **Certificate error**: either install/trust an appropriate endpoint
  certificate or disable certificate verification for the local connection.
- **Unsupported response**: download integration diagnostics, redact them once
  more before sharing, and include model and firmware in a GitHub issue.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and safe fixture rules.
Use `scripts/probe_endpoint.py --help` for the read-only endpoint probe. Never
publish unredacted device dumps or credentials.

## Licence

Copyright © 2026 Daniel Wilson ([@Danw33](https://github.com/Danw33))

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). 
The licence covers this project's code and documentation; it does not grant rights to third-party
trademarks, firmware, documentation, or other materials.

Crestron and DM NVX are trademarks of their respective owners.
