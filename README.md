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

The project is under private development until its security, license, migration,
and clean-history audits pass. Do not expose a development repository publicly.

## Design boundary

The Frappe app decides whether the current user may read, print, and send a
record. The private gateway has no public TCP port and only accepts signed
requests over a Unix-domain socket. Credentials and linked-device state never
enter the Frappe database, Git repository, normal site backup, or PDF payload.

## Planned installation

```sh
bench get-app https://github.com/webmoxter/erpnext-whatsapp-connection
bench --site your-site.example install-app erpnext_whatsapp_connection
```

The gateway container and two secret files must also be installed using the
versioned deployment example that will ship with the first audited release.

## License and provider notice

The add-on is GPL-3.0. The bundled gateway uses Baileys under the MIT
license and can alternatively use Meta's official WhatsApp Business Cloud API.
Baileys is unofficial and may carry account-policy risk. This project prohibits
bulk marketing, number scraping, anti-spam evasion, and sending without a valid
business purpose and recipient consent.
