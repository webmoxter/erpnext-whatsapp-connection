# ERPNext WhatsApp Connection by ERPFin360.com

> Independent third-party software maintained by ERPFin360.com. This project is not
> affiliated with, sponsored by, or endorsed by Frappe Technologies, ERPNext,
> Meta, or WhatsApp. Product names are used only to describe compatibility.

An installable Frappe/ERPNext add-on for permission-checked document and report
delivery through WhatsApp. It provides:

- **Send by WhatsApp** actions on supported documents and reports;
- customer/contact number selection;
- print-format selection and PDF preview;
- site-managed message templates;
- a durable outbound queue with retries and delivery history;
- linked-device and official WhatsApp Business Cloud API transports;
- an extension contract for custom applications and reports.

The outbound transport is also replaceable through
`erpnext_whatsapp_transport_adapter_providers`. This keeps the document workflow
independent from a particular WhatsApp library. The official Frappe WhatsApp
application can be integrated through this contract after it publishes a stable,
versioned release; it is not silently downloaded from an untagged development branch.

Releases are published from signed semantic-version tags. GitHub release
immutability, checksummed Python/source artifacts, a digest-pinned gateway image,
and a machine-readable release manifest form the supported supply-chain contract.

## Design boundary

The Frappe app decides whether the current user may read, print, and send a
record. The private gateway has no public TCP port and only accepts signed
requests over a Unix-domain socket. Credentials and linked-device state never
enter the Frappe database, Git repository, normal site backup, or PDF payload.

## Installation

```sh
bench get-app --branch v0.1.0 https://github.com/webmoxter/erpnext-whatsapp-connection
bench --site your-site.example install-app erpnext_whatsapp_connection
```

For production, verify the immutable release and its assets before installation,
pin the gateway by digest from `release-manifest.json`, and follow
[`docs/INSTALLATION.md`](docs/INSTALLATION.md). Never install from a moving branch.

## Compatibility and upgrades

- Supported: Frappe 16 and ERPNext 16 on Python 3.14 and Node 24.
- Each site owns separate settings, templates, history, credentials, and gateway state.
- Upgrade with a protected backup, a signed release, `bench update --reset`, and
  `bench --site <site> migrate`.
- Extension hooks are versioned public API. Breaking changes require a new major version.

See [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md),
[`docs/RELEASES.md`](docs/RELEASES.md), and [`CHANGELOG.md`](CHANGELOG.md).

## License and provider notice

The add-on is GPL-3.0. The bundled gateway uses Baileys under the MIT
license and can alternatively use Meta's official WhatsApp Business Cloud API.
Baileys is unofficial and may carry account-policy risk. This project prohibits
bulk marketing, number scraping, anti-spam evasion, and sending without a valid
business purpose and recipient consent.
