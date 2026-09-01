# Production installation

## 1. Verify the release

Use an immutable GitHub release whose signed tag, commit, asset attestations, and
`release-manifest.json` all agree. Verify downloaded assets with GitHub CLI and
their SHA-256 values in the manifest. Do not install from `main`.

## 2. Back up the site

Create and verify a complete database and private/public file backup before
installing or upgrading the application.

## 3. Install the Frappe application

```sh
bench get-app --branch v0.1.2 https://github.com/webmoxter/erpnext-whatsapp-connection
bench --site your-site.example install-app erpnext_whatsapp_connection
bench --site your-site.example migrate
```

## 4. Deploy the gateway

Run the gateway image from the exact digest in the release manifest. Mount:

- a private Unix-socket directory shared only with Frappe web/workers;
- a persistent linked-device authentication volume;
- a persistent encrypted state volume;
- a 32-byte-or-longer HMAC secret file;
- a separate 32-byte-or-longer authentication-encryption secret file.

Do not publish a TCP port. The gateway refuses sockets outside
`/run/erpnext-whatsapp`.

Set matching `ERPNEXT_WHATSAPP_SOCKET` and
`ERPNEXT_WHATSAPP_HMAC_KEY_FILE` values in Frappe web, worker, and scheduler
processes. Secret contents must never enter environment variables, site config,
logs, backups, or source control.

## 5. Configure and verify

Grant `ERPNext WhatsApp Manager` only to administrators and
`ERPNext WhatsApp Sender` only to approved users. Configure one provider, connect
it, send to an authorized internal number, and confirm the private PDF checksum
and delivery-history entry before enabling normal use.

## Upgrade and rollback

Upgrade only from a signed immutable tag and run `migrate`. If a database
migration fails, stop sending and restore the protected pre-upgrade backup with
the former pinned application and gateway image. Never delete delivery history
to make an upgrade pass.
