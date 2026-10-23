# Changelog

This project follows Semantic Versioning.

## 0.1.5 — release preparation

- Add opt-in, company-specific Linked Device group copies and joined-group
  selection in WhatsApp settings, with current company/source/sender checks.
- Separate copy history, private snapshots and retry identity from the primary;
  block uncertain group submission replay using durable per-part checkpoints.
- Preserve configured zero retries and keep existing installations disabled.
- Route trusted ordinary CI to the separately registered GCP WhatsApp test lane;
  retain signed immutable publication controls and public-fork isolation.
- Prepare native Warehouse Type prerequisites for the disposable Company
  preservation fixture, retaining native validation and rollback on errors.

Native end-to-end group delivery/browser acceptance remains pending. Signing,
publication and consumption remain blocked until that acceptance is complete;
this preparation entry does not publish artifacts or claim live delivery proof.

## 0.1.4

- Enforce a hard delivery-attempt ceiling of one initial attempt plus the configured automatic retries.
- Stop exhausted deliveries from retaining a stale retry timestamp that can trigger repeated scheduler enqueueing.
- Prevent duplicate or stale workers from bypassing Processing state or retry backoff.
- Claim due retries before enqueueing and restore retry eligibility if enqueueing itself fails.

## 0.1.3

- Allow a registered report adapter to provide a permission-checked PDF renderer.
- Exclude hidden report columns from the generic PDF fallback.

## 0.1.2

- Normalize gateway submission and acknowledgement timestamps before storing
  them in Frappe Datetime fields.

## 0.1.1

- Establish TNGSol.com as the sole public project owner, original Git initiator,
  product brand, and maintainer.

## 0.1.0

- Add permission-checked WhatsApp delivery for supported ERPNext documents and reports.
- Add customer/contact number selection, editable templates, print-format selection,
  PDF preview, a durable queue, retries, and delivery history.
- Add linked-device and official WhatsApp Business Cloud API transports.
- Add public adapter contracts for custom documents, reports, and transports.
- Add a private Unix-socket gateway with signed replay-resistant requests.
- Add signed, immutable, checksummed release publication.
