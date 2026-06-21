# Developer Agent Guide for octoDNS Hetzner Provider

This repository contains the Hetzner provider for octoDNS. It enables planning, syncing, and applying DNS record states directly to either Hetzner DNS API or Hetzner Cloud (hcloud) DNS services.

> [!IMPORTANT]
> **Core Workflow and Guidelines**
>
> All agents working on this repository must read and follow the general instructions and workflow guidelines defined in the core octoDNS `AGENTS.md` file.
> - **Local check**: Look for the file at `../octodns/AGENTS.md`.
> - **Remote check**: If the local file is not available, fetch it from GitHub: [octoDNS Core AGENTS.md](https://github.com/octodns/octodns/raw/refs/heads/main/AGENTS.md).
>
> You must align your code structure, style, pull request guidelines, and overall development workflows with the instructions specified there.

## Repository & Module Information

### Key Components

- **Provider Class**: [HetznerProvider](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/__init__.py#L43-L498) (defined in [octodns_hetzner/__init__.py](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/__init__.py)). Dynamically initializes client adaptors and update strategies depending on the selected backend configuration.
- **Client Adapters**:
  - [HetznerClient](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/dnsapi_client.py) (defined in [octodns_hetzner/dnsapi_client.py](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/dnsapi_client.py)) connects to the standard Hetzner DNS API (`https://dns.hetzner.com/api/v1`).
  - [HCloudZonesClient](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/hcloud_adapter.py) (defined in [octodns_hetzner/hcloud_adapter.py](file:///home/ross/octodns/octodns-hetzner/octodns_hetzner/hcloud_adapter.py)) integrates with Hetzner Cloud (hcloud) DNS services.

### Key Workflows & Features

1. **Supported Record Types**: `A`, `AAAA`, `CAA`, `CNAME`, `DS`, `MX`, `NS`, `PTR`, `SRV`, `TLSA`, `TXT`.
2. **Backends**: Configured via the `backend` argument:
   - `dnsapi`: Targets standard public Hetzner DNS zones (uses Bearer Token authentication).
   - `hcloud`: Targets Hetzner Cloud platform DNS.
3. **Root Name Server Support**: Fully supported (`SUPPORTS_ROOT_NS=True`).
4. **Dynamic Routing**: Not supported (`SUPPORTS_DYNAMIC=False`, `SUPPORTS_GEO=False`).
5. **Dynamic Subnets**: Not supported (`SUPPORTS_DYNAMIC_SUBNETS=False`).
6. **Pool Value Status**: Not supported (`SUPPORTS_POOL_VALUE_STATUS=False`).

## Development & Testing

- **Setup Script**: Run `./script/bootstrap` to create a virtual environment, install runtime and development dependencies (including `black`, `isort`, `pyflakes`, and `pytest`), and configure pre-commit hooks.
- **Test Suite**: Run unit tests using `pytest` via `./script/test` (or `pytest tests/`). Test files are located in [tests/](file:///home/ross/octodns/octodns-hetzner/tests).
- **Code Coverage**: Verify code coverage using `./script/coverage`.

## Key Constraints & Behaviors

- **Python Version**: Targets Python `>=3.8`.
- **Formatting**: Code formatting is enforced via `black` (version `>=26.0.0,<27.0.0`) and `isort`.
