# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses semantic versioning for releases.

## [Unreleased]

### Fixed

- Normalize built-in A/V port labels to sentence case (for example, `INPUT 1`
  becomes `Input 1`). A topology-confirmed zero-based group label such as
  `output0` displays as `Output 1`. Custom labels, raw API data, stable unique
  IDs and existing entity IDs remain unchanged; no library update is required.
- Filter discovery suggestions against every resolved IPv4 address of configured
  hostnames, independently of device display names. Remove matching stale cards
  on subsequent scans and after authenticated setup.
- Reject authenticated duplicate setup by REST device ID or an unambiguous
  matching model/serial number without replacing the existing connection host.
  UDP names alone cannot identify previously unknown alternate interfaces.
- Publish IPv4 scan results in Home Assistant's Discovered section as soon as
  scanning finishes, even if the scanning dialog is closed without adding a
  device. Successful setup removes the matching pending card; other candidates
  remain available without another scan.

## [0.5.0]

### Fixed

- A/V port entities keep stable identities when firmware regenerates port UUIDs
  on every poll, preventing unavailable entities and repeated registrations.
- Conservatively migrate the oldest recognised legacy entity for each
  unambiguously labelled physical port/metric, retaining its entity ID and
  customisations. Surplus or ambiguous entries remain for manual review.

### Added

- Separate transmit active-bitrate diagnostic entities; missing measurements
  remain unknown instead of falling back to the reported bitrate.

### Changed

- Existing bitrate entities show the raw API `Bitrate` field and are labelled
  "reported bitrate". Their historical transmit readings may have mixed active
  and reported values. No values are clamped or inferred from stream status.
- Device-ready, codec-ready and reported-bitrate diagnostics are disabled by
  default for newly registered entities. Existing enable/disable choices persist.
- Require `crestron-nvx==0.3.0`

## [0.4.0]

### Added

- Deferred setup flows for the remaining devices from a scan, surfaced in Home
  Assistant's Discovered section so each can be configured without rescanning.
- Authenticated REST identity remains authoritative when creating entries; the
  temporary discovery key is used only for the pending flow and HA's Ignore
  handling.

## [0.3.0]

### Added

- On-demand read-only UDP discovery during setup, using HA's enabled IPv4
  interfaces or an explicitly selected address/subnet (at most /24).
- Candidate labels with hostname, model and source IP, plus optional reported
  firmware and build date before authenticated setup.
- Bounded, paced queries; fixed reply-port handling; cancellation cleanup;
  duplicate protection through authenticated REST identity.
- Discovery provenance, inspiration credit, network guidance and synthetic
  parser, transport and config-flow tests.

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
