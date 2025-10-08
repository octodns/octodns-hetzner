## Hetzner DNS provider for octoDNS

An [octoDNS](https://github.com/octodns/octodns/) provider that targets [Hetzner DNS](https://www.hetzner.com/dns-console).

### Installation

#### Command line

```
pip install octodns-hetzner
```

#### requirements.txt/setup.py

Pin specific versions or SHAs in your project to control upgrades. Refer to
PyPI for current releases. Minimum requirements align with `setup.py`, e.g.:

```
octodns>=1.5.0
octodns-hetzner>=1.0.0
```

### Configuration

```yaml
providers:
  hetzner:
    class: octodns_hetzner.HetznerProvider
    # Your Hetzner API token (required)
    token: env/HETZNER_TOKEN
    # Choose backend during transition to Cloud Zones API
    # - dnsapi (default): uses Hetzner DNS Console API (current behavior)
    # - hcloud: uses Hetzner Cloud API (Zones). Requires a Cloud API token
    backend: dnsapi
```

### Backends

- `dnsapi` (default): uses Hetzner DNS Console API with DNS tokens. Backward compatible with existing setups.
- `hcloud`: uses Hetzner Cloud API Zones via the official `hcloud` client. Requires a Hetzner Cloud API token. The `hcloud` client library is installed as a dependency of this package.

Both backends will co-exist until at least May 2026. The default remains `dnsapi`; opt into `hcloud` when ready.

Note: The `hcloud` backend is new and may evolve. Apply (writes) are implemented via RRSet semantics in the provider, with a thin adapter using the official `hcloud` client. When zone/rrset TTLs are unavailable from the API, a conservative fallback of `3600` seconds is used.

### Zone-by-Zone Migration

You can configure multiple provider instances with different backends to migrate zones gradually:

```yaml
providers:
  hetzner-dns:
    class: octodns_hetzner.HetznerProvider
    token: env/HETZNER_DNS_TOKEN
    backend: dnsapi

  hetzner-cloud:
    class: octodns_hetzner.HetznerProvider
    token: env/HETZNER_CLOUD_TOKEN
    backend: hcloud

zones:
  # Legacy zone still using DNS Console API
  legacy.example.com.:
    sources:
      - hetzner-dns
    targets:
      - hetzner-dns

  # Zone migrated to Cloud Zones API
  migrated.example.com.:
    sources:
      - hetzner-cloud
    targets:
      - hetzner-cloud
```

**Migration Steps**:

1. **Prepare**: Ensure you have a Hetzner Cloud API token available for `hcloud`.
2. **Configure**: Add a second provider instance with `backend: hcloud` and the Cloud API token
3. **Test**: Run `octodns-sync --dry-run` to validate the new provider can read zones
4. **Migrate**: Update zone configuration to use the new provider
5. **Verify**: Confirm DNS records are identical using `octodns-compare`
6. **Repeat**: Migrate remaining zones one at a time

**Token Requirements**:
- `dnsapi` backend: Requires DNS Console API token (from DNS Console)
- `hcloud` backend: Requires Hetzner Cloud API token (from Cloud Console)
- Tokens are **not interchangeable** between backends

### Support Information

#### Records

HetznerProvider supports A, AAAA, CAA, CNAME, DS, MX, NS, PTR, SRV, TLSA, and TXT

#### Root NS Records

HetznerProvider supports full root NS record management.

#### Dynamic

HetznerProvider does not support dynamic records.

### Development

See the [/script/](/script/) directory for some tools to help with the development process. They generally follow the [Script to rule them all](https://github.com/github/scripts-to-rule-them-all) pattern. Most useful is `./script/bootstrap` which will create a venv and install both the runtime and development related requirements. It will also hook up a pre-commit hook that covers most of what's run by CI.
