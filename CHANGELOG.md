# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and intends to use semantic versioning after its first release.

## [Unreleased]

## [0.2.0]

### Added

- Capability-driven image entity using the crestron-nvx 0.2.0 client.
- Bounded authenticated JPEG retrieval, 30-second caching and failure throttling.
- Preview failures isolated from sensors; dynamic capability discovery.
- Opt-in `--preview` probe and pre-release hardware checklist.
- Firmware 1 DM-NVX-350 API-shape evidence; HA testing pending.
- Largest-first preview selection and case-insensitive local-hosting detection.
- Self-contained private test ZIP builder; release artifacts retain the PyPI dependency.
- DM-NVX-360 firmware 7.1 preview display, updates, Media and remote iOS
  viewing confirmed by the user.

## [0.1.0]

### Added

- Greenfield Home Assistant custom integration under the `crestron_nvx` domain.
- Read-only async API boundary for endpoint identity and device-specific state.
- Config, reauthentication, and reconfiguration flows.
- Sensor, binary-sensor, diagnostics, and Phase 2 image scaffolding.
- Tests, linting, strict typing, HACS/hassfest validation, and project docs.
- Firmware 7.1 integer/boolean compatibility for `DeviceReady`.
- Typed source and configuration status entities observed on DM-NVX-350.
- Privacy-minimized probing of documented A/V, stream, and preview objects.
- Typed Phase 1 input-sync, output-connection/transmission, resolution, stream
  status, codec-readiness, and bitrate entities based on a sanitized
  DM-NVX-350 firmware 7.1 response shape.
- DM-NVX-360 firmware 7.1 shape validation and configured-bitrate fallback when
  an endpoint omits `ActiveBitrate`.
- DM-NVX-E30 firmware 6.0 response-shape validation and an explicit support
  matrix covering firmware 6.0 and 7.1 on the 350, 360, and E30.
- Explicit public-API provenance and clean-source documentation, with links to
  Crestron's official DM NVX REST API and authentication references.
- Published `crestron-nvx==0.1.0` client adopted as the integration's pinned
  protocol dependency.
- Documented a dependency-free manual ZIP workflow for private pre-release
  Home Assistant testing.
- Successfully validated hostname-based setup and creation of 53 field-driven
  entities on a real firmware 7.1 DM-NVX-360.
- Bounded JSON response reads and endpoint-controlled entity collections.
- Full config-flow helper coverage and privacy regression tests for the probe.
- Original generic AV-over-IP brand icon for HACS installations.
- Immutable commit targeting for HACS pull-request validation.

### Security

- Disabled automatic HTTP redirects during the authentication bootstrap.
- Replaced heuristic probe redaction with an allowlist of public schema keys.
- Expanded the setup and documentation warning shown when certificate
  verification is disabled for self-signed endpoints.
