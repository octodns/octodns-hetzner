## Hetzner DNS provider for octoDNS

An [octoDNS](https://github.com/octodns/octodns/) provider that targets [Hetzner DNS](https://docs.hetzner.com/networking/dns/).

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
    # Your Hetzner Cloud API token (required)
    token: env/HETZNER_TOKEN
```

The provider uses the Hetzner Cloud API through the official `hcloud` client,
which is installed as a dependency of this package. Create the token in the
[Hetzner Console](https://console.hetzner.com/). When zone or RRSet TTLs are
unavailable from the API, the provider uses a fallback of `3600` seconds.

### Migrating from 2.x

Hetzner shut down the legacy DNS Console API (`dns.hetzner.com`) in May 2026,
and version 3.0 removes the `dnsapi` backend that used it. To upgrade:

1. Replace the DNS Console token with a Hetzner Cloud API token. The two token
   types aren't interchangeable, so an old DNS Console token fails with an
   authentication error.
2. Remove `backend: dnsapi` from your provider configuration. The provider
   raises an error at startup if it's still set. `backend: hcloud` is still
   accepted, so configurations that already set it keep working.
3. Run `octodns-sync` without `--doit` and confirm the plan shows no unexpected
   changes.

### Support Information

#### Records

HetznerProvider supports A, AAAA, CAA, CNAME, DS, MX, NS, PTR, SRV, TLSA, and TXT

#### TXT Records and DKIM

Long TXT records (such as DKIM keys exceeding 255 characters) are automatically
chunked into RFC-compliant format. For DKIM keys, configure them as a single TXT
value in your zone file:

```yaml
dkim._domainkey:
  type: TXT
  value: "v=DKIM1\\;k=rsa\\;p=MIIBIjANBgkqh...very-long-key..."
```

The provider will automatically split values exceeding 255 characters into
properly quoted chunks (e.g., `"chunk1" "chunk2"`). Do not manually split long
values into multiple `values:` entries unless you specifically need multiple
distinct TXT records (such as for site verification).

#### Root NS Records

HetznerProvider supports full root NS record management.

#### Dynamic

HetznerProvider does not support dynamic records.

### Development

See the [/script/](/script/) directory for some tools to help with the development process. They generally follow the [Script to rule them all](https://github.com/github/scripts-to-rule-them-all) pattern. Most useful is `./script/bootstrap` which will create a venv and install both the runtime and development related requirements. It will also hook up a pre-commit hook that covers most of what's run by CI.
