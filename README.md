# Crestron DM NVX for Home Assistant

[![CI](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/ci.yml)
[![Home Assistant validation](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml/badge.svg)](https://github.com/Danw33/ha-crestron-nvx/actions/workflows/validate.yml)
[![Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

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

This integration communicates through Crestron's **publicly accessible and
publicly documented DM NVX REST API**. It was not produced by extracting
confidential or private information and does not depend on reverse-engineered
wire formats.

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

The repository is a functional, read-only foundation, not yet a user release.
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
- reserves an empty image platform for a later preview-image entity.

There are deliberately no write/control operations. No reboot, routing, mode,
input, stream, or device-configuration command can be sent by this version.

## Roadmap

1. Complete Phase 1 status coverage using sanitized observations from each
   target model, including stream, input-sync, and output-sync state.
2. Add a Home Assistant image entity for supported preview JPEGs.
3. Design separately reviewed, explicitly guarded control entities/actions.
4. Add stream-to-endpoint selection with a Home Assistant-native UX.

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

HACS installation will be available after the repository has a public GitHub
release. Until then, advanced testers can add the GitHub repository as a custom
HACS integration repository.

## Configuration

The setup flow asks for:

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

A manual Home Assistant installation has successfully configured a firmware
7.1 DM-NVX-360 by hostname and created one device with 53 field-driven entities
covering the returned device, source, port, and stream status. See the
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
- Automatic discovery and preview images are not implemented.
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
