# ERPNext WhatsApp Connection by TNGSol.com

**Project owner, original Git initiator, and maintainer: [TNGSol.com](https://tngsol.com)**

> Independent third-party software maintained by TNGSol.com. This project is not
> affiliated with, sponsored by, or endorsed by Frappe Technologies, ERPNext,
> Meta, or WhatsApp. Product names are used only to describe compatibility.

An installable Frappe/ERPNext add-on for permission-checked document and report
delivery through WhatsApp. It provides:

- **Send by WhatsApp** actions on supported documents and reports;
- customer/contact number selection;
- print-format selection and PDF preview;
- site-managed message templates;
- a durable outbound queue with retries and delivery history;
- opt-in company-specific Linked Device group copies with independent history;
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

## Optional document notifications (Pilot-compatible Frappe integration)

An **opt-in, disabled-by-default** automation layer can propose WhatsApp
notifications when submitted **Sales Invoices** or customer-receipt
**Payment Entries** meet a company-specific rule. Modes:

- **Approval Required** (recommended): a WhatsApp manager reviews the exact
  message and source document in **ERPNext WhatsApp Automation Request**,
  then explicitly approves or rejects it.
- **Send Automatically**: an administrator expressly enables this mode for a
  particular company and supported document type.

Both modes require recorded Customer consent, a validated linked recipient
number, company/source permissions and current print access. Dispatch reuses
the **existing** private PDF + durable outbound queue; the manual
**Send by WhatsApp** actions and optional company group copies stay intact.
No automation, backfill or live sends begin on installation.

See [Pilot setup and automation guide](docs/PILOT_AUTOMATION.md). Frappe Pilot
manages the application site, **not** the separate private WhatsApp gateway;
transport connectivity must be configured and tested independently.

## Design boundary

The Frappe app decides whether the current user may read, print, and send a
record. The private gateway has no public TCP port and only accepts signed
requests over a Unix-domain socket. Credentials and linked-device state never
enter the Frappe database, Git repository, normal site backup, or PDF payload.

## Installation

```sh
bench get-app --branch v0.1.3 https://github.com/webmoxter/erpnext-whatsapp-connection
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

Company copies and their current evidence/release limits are described in
[`docs/GROUP_COPIES.md`](docs/GROUP_COPIES.md). Ordinary GCP CI runner setup is
documented in [`docs/SELF_HOSTED_CI.md`](docs/SELF_HOSTED_CI.md).

## License and provider notice

The add-on is GPL-3.0. The bundled gateway uses Baileys under the MIT
license and can alternatively use Meta's official WhatsApp Business Cloud API.
Baileys is unofficial and may carry account-policy risk. This project prohibits
bulk marketing, number scraping, anti-spam evasion, and sending without a valid
business purpose and recipient consent.
