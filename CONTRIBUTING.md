# Contributing

Thank you for helping build reliable local DM NVX support for Home Assistant!

## Development

Use Python 3.14, create a virtual environment, and install
`requirements-test.txt`. Before opening a pull request, run:

```console
ruff format --check .
ruff check .
mypy
pytest --cov=custom_components.crestron_nvx
```

Every behaviour change should include tests. Coverage must stay above 95%, and
config-flow branches should be fully covered.

## Safe endpoint research

Research must remain read-only until control support is designed and approved:

- use `GET` requests for HTTP endpoint research;
- discovery may send only the identification query described in
  [DISCOVERY.md](docs/DISCOVERY.md), within an explicitly selected scope;
- never probe undocumented paths by sending mutating HTTP methods;
- never send empty API objects;
- test only equipment and networks you are authorized to access;
- remove credentials, cookies, tokens, device IDs, serial numbers, MAC
  addresses, IP addresses, hostnames, and personal names before sharing data;
- convert observations into minimal synthetic test fixtures rather than
  committing raw device responses or packet captures.

The implementation is based on Crestron's publicly accessible, publicly
documented DM NVX REST API plus ordinary compatibility testing against
equipment contributors are authorized to administer. Do not copy vendor
manuals, API reference pages, sample payloads, firmware, web assets, schemas,
private SDK material, decompiled code, or proprietary source into this
repository. Link to public documentation and write original interoperability
code and descriptions. See [API_PROVENANCE.md](docs/API_PROVENANCE.md).

## Scope

REST protocol concerns and typed API data belong in the standalone
[`crestron-nvx`](https://github.com/Danw33/py-crestron-nvx) library. Home
Assistant platform code should depend on its typed snapshot, not vendor JSON.
The small UDP discovery implementation currently lives in the integration's
`discovery.py`, separate from config-flow/UI logic. It uses HA's network
interface preferences and may be extracted when other product families are
validated consumers. Do not add a dependency on proprietary SDKs.

Control/write proposals should be isolated from monitoring changes, document
their safety and failure behaviour, and include tests proving that setup,
polling, diagnostics, and removal remain non-destructive.
