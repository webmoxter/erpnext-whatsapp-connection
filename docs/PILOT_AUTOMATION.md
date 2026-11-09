# Opt-in automatic document notifications and Frappe Pilot

This feature **does not replace** the existing **Send by WhatsApp** button, private
gateway, PDF snapshot, retry worker, or history. It adds a site-local decision
layer which proposes one notification when a permitted customer **Sales Invoice**
or **customer Receive Payment Entry** is submitted.

## Security defaults

- All automation starts **disabled**, including every new company rule.
- Existing tenant settings, manually queued messages, and group copies remain unchanged.
- There is no guest send endpoint or caller-selected arbitrary DocType.
- A matching **per-company** rule is required. Only two specified submit hooks
  are supported; adding a child-table entry cannot invent a new Frappe hook.
- The Customer must have three fields populated by an authorized business user:
  **Automatic WhatsApp Documents: Customer Opt-in Confirmed** checked,
  **Automatic WhatsApp Recipient** set to an international number, and a
  **WhatsApp Consent Evidence Reference**. The number must still resolve
  to that Customer or a currently permission-visible linked Contact.
- Consent covers a specific document-notification purpose. Confirm the
  customer's authorization and the WhatsApp provider's messaging policies.
  These fields are not authorization to send marketing messages.
- The submitting user must be active and have current Read/Print permission
  on the source document. A manager approving a request must have the same
  permission. The worker rechecks authorization, Company, source version,
  recipient, consent, template, and message before queuing.
- The proposal contains a masked number and a recipient fingerprint rather
  than an unencrypted phone number. The exact text to be sent is frozen for
  approval. A changed phone/source/template blocks the proposal; make a new
  manual send rather than overriding that check.
- One site-local deterministic request exists per submitted document. A locked
  request and an after-commit job prevent duplicate approval and dispatch.
- Automatic notifications never add company WhatsApp-group copies. Explicit
  manual group copies retain their separate opt-in workflow.
- No backfill runs on installation, migration, or enabling a rule. Past
  documents are never sent automatically.
- In the event of a blocked request, **nothing is sent**. Review the non-secret
  reason on the automation request and use the existing manual composer if
  a newly authorized message is needed.

## Configuration

On an isolated test tenant, as an authorized System Manager / ERPNext WhatsApp
Manager:

1. Verify the private gateway and WhatsApp provider are intentionally configured;
   transport setup is separate from installing this Frappe application.
2. Record a consenting **Customer** and an authorized customer/contact phone
   number. Set all three Customer fields listed above. **Do not use live
   customer or WhatsApp numbers in the pilot tests.**
3. Open **ERPNext WhatsApp Settings**, enable the transport if testing with a
   synthetic capture gateway, and enable **Enable Document Automation**.
4. In **Company Automation Rules**, add the specific Company, choose
   **Sales Invoice** or **Payment Entry**, and enable the rule.
5. Set **Delivery Mode = Approval Required** first. A matching submitted
   synthetic document creates a read-only **ERPNext WhatsApp Automation Request**
   with status **Pending Approval**; it does not enqueue a delivery yet.
6. Review the original document and the **Message for approval** shown on the
   request. Click **Approve and queue** or **Reject**. Approval revalidates
   authorization, consent and the exact content; dispatch then uses the existing
   private PDF queue and Delivery History.
7. After safe end-to-end validation, an authorized manager may explicitly
   switch the specific company rule to **Send Automatically**. That still
   requires the global automation switch, recipient consent, document and print
   permissions, and exact content verification.
8. Confirm duplicate hook invocation creates no second request. Confirm
   unchanged permission denial, consent revocation, number modification,
   source modification, and rule disablement block dispatch.

**Do not enable automatic live messages during initial Pilot testing.**

## Pilot bench integration

Pilot v0.0.99-pre-alpha can install Frappe applications onto individual sites;
it does **not** automatically provision this add-on's private Node gateway.
Both are necessary for real delivery.

The following are examples for an approved **disposable** tenant on the
existing bench, not commands to run against existing tenant sites.

```sh
sudo -iu frappe /home/frappe/pilot/bin/pilot \
  -b erpfin360-lab get-app \
  https://github.com/webmoxter/erpnext-whatsapp-connection \
  --branch feature/optional-consented-auto-notifications-pilot

# Create a disposable site through Pilot Admin, selecting ERPNext and this app,
# or create it with the documented Pilot new-site command and explicit apps.
sudo -iu frappe /home/frappe/pilot/bin/pilot \
  -b erpfin360-lab list-site-apps YOUR-DISPOSABLE-SITE.localhost
```

Do not install an unreleased branch on production. Pin a verified tagged
release for production only after a signed release, full CI and independent
security acceptance. Installing with Pilot's Admin UI also requires that the
app is first present on the bench.

### Private gateway requirements

Follow [production installation](INSTALLATION.md) for gateway protocol and
release verification. Frappe/Pilot's web and RQ worker processes must have
authorized access to a **private Unix socket** (default under
`/run/erpnext-whatsapp`) and a matching secret file via
`ERPNEXT_WHATSAPP_SOCKET` and `ERPNEXT_WHATSAPP_HMAC_KEY_FILE`.

On a Pilot systemd-managed bench, inspect service ownership, worker pools,
socket visibility, permissions, restart behavior and recovery before selecting
a gateway deployment strategy. Docker/container mounts or sidecar services
must not publish a TCP gateway port. Never commit HMAC keys, QR authentication
state, linked-device credentials, Meta tokens, message bodies or PDF snapshots.

Pilot may reuse the existing private gateway, but integration is **NOT VERIFIED**
until a real disposable site uses the signed local transport and runs the
end-to-end native permission/queue checks. Frappe package installation alone
is not proof of a working WhatsApp transport. Keep `localhost:7000` and
`localhost:8000` behind SSH forwarding.

## Rollback and compatibility

1. Before installation, make a verified full site backup (database, public and
   private files, site-specific encryption key) and record all app revisions.
2. Disable **Enable Document Automation** to stop new proposals.
3. Do not delete completed or pending Delivery History to hide a failure.
4. For a code/schema rollback, use the verified pre-upgrade backup and prior
   signed application/gateway revision. Uninstall is **not** a database rollback.
5. Do not change ERPNext, Frappe, Pilot, or the source business application.

Frappe 16 / ERPNext 16 / Python 3.14 are declared target versions. Native
installation and focused policy tests must pass on the exact Pilot target
before production compatibility can be claimed.

This feature does not implement campaign marketing, payment reminders, a
chatbot, or free-form phone sending. The official Meta API may require
pre-approved templates and permitted conversation windows; a queued
notification does not guarantee Meta will accept it.
