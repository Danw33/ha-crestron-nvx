# Crestron DM NVX for Home Assistant

[![CI](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml)
[![Home Assistant validation](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FDanw33%2Fha-crestron-nvx%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)

An early-stage custom integration for direct, local monitoring of Crestron
DM NVX AV-over-IP endpoints. The initial supported devices are DM-NVX-350,
DM-NVX-360, and DM-NVX-E30 endpoints running firmware 6.0 or 7.1.

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

Monitoring and previews communicate through Crestron's **publicly accessible
and publicly documented DM NVX REST API**. The optional UDP discovery probe
uses public research and hardware interoperability observations, described in
[discovery and protocol provenance](docs/DISCOVERY.md). No confidential or
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

Version 0.6.0 prepares immediate discovery cards, 
improved IPv4 hostname/identity matching, and consistent built-in port labels. 

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

There are deliberately no write/control operations. No reboot, routing, mode,
input, stream, or device-configuration command can be sent by this version.

## Roadmap

1. Complete Phase 1 status coverage using sanitized observations from each
   target model, including stream, input-sync, and output-sync state.
2. Complete preview lifecycle and 0.6.0 discovery/port-label hardware checks.
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

### Development checkout

Copy `custom_components/crestron_nvx` into the `custom_components` directory in
your Home Assistant configuration, restart Home Assistant, then add
**Crestron DM NVX** from **Settings → Devices & services → Add integration**.

A disposable ZIP can also be built for testing before publication. See
[manual pre-release installation](docs/MANUAL_TESTING.md).

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

Configured hostnames are matched through all their current IPv4 DNS answers,
not device display names. Authenticated duplicate setup checks REST identity
and, when unambiguous, model/serial number, without replacing existing settings.

The connection form asks for:

- **Host name or IP address**: local management address of one endpoint;
- **Username and password**: a device account allowed to read the API;
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

DM-NVX-350, DM-NVX-360, and DM-NVX-E30 on firmware 6.0 and 7.1 are the declared
initial support scope. The shared API shape across these models and firmware
families is assumed until every combination can be tested directly.

| Model | Firmware 6.0 | Firmware 7.1 |
| --- | --- | --- |
| DM-NVX-350 | Supported; validation pending | Supported; hardware validated |
| DM-NVX-360 | Supported; validation pending | Supported; HA setup validated |
| DM-NVX-E30 | Supported; hardware validated | Supported; validation pending |

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
becomes `Output 1`. Custom labels and existing entity IDs are preserved. See the
[hardware validation record](docs/HARDWARE_VALIDATION.md) for what this proves
and which lifecycle tests remain outstanding.

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
- No device control is implemented.

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
The first real-hardware check is documented in
[docs/ENDPOINT_PROBING.md](docs/ENDPOINT_PROBING.md).

## Licence

Copyright © 2026 Daniel Wilson ([@Danw33](https://github.com/Danw33))

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). 
The licence covers this project's code and documentation; it does not grant rights to third-party
trademarks, firmware, documentation, or other materials.

Crestron and DM NVX are trademarks of their respective owners.
