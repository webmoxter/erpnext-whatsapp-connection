# Company group copies

This feature is opt-in for each company. Existing installations have no group
rules and gain no extra recipients. In WhatsApp Settings, choose Linked Device,
use **Configure Company Group**, select a permitted company, load joined groups,
select one, and explicitly enable its rule before saving. A different company
never inherits that rule. A disabled row may be retained for later setup.

Group discovery requires current native WhatsApp Settings Write plus Company
Read. Saving changes, including deleting another company's rule, checks the
affected companies. These are configured/native permissions, not eligibility
based on a business-role label. The connected account must currently belong
to the selected group; announcement groups require posting authority. The
group selection endpoint never returns participants or other tenants' groups.
Only Linked Device is implemented for groups. Official API group copies are
rejected; disable the rules before switching to that provider. Nothing routes
a group identifier through the individual phone-number API.

## Sending and history

The source document/report determines the company on the server. The composer
warns when a company copy is configured. An API caller cannot substitute a
different company/group. Primary and copy get separate encrypted-recipient,
private-PDF, history, attempt and idempotency records. The copy waits for its
primary to succeed, and then rechecks the original enabled sender, source,
company, current configuration, PDF identity and document version. Revoking
sender/source access or changing the configured group blocks the queued copy.
The existing report adapter and consuming application's record/output guards
remain authoritative; upgrading consumers must validate their extensions.

Retrying a failed copy never invokes the primary send. The gateway records each
confirmed group PDF/text part and writes an in-flight marker before making its
provider call. A missing acknowledgement, interrupted send or uncertain outcome
sets/requires reconciliation and blocks automatic replay. It does not assert
that the message was not sent. Reconciliation-required records have no unsafe
"force resend" action; operator investigation is required. A new send must not
be used as an automatic workaround. This does not redesign older individual
delivery's retry semantics.

No copy-of-copy is supported. Company/provider/owner/source/filter/template/
snapshot bindings must match the original. Group IDs are stored only in the
site's access-controlled settings and encrypted history recipient, never in
logs or source. No production account, group or recipient is contacted by tests.

## Evidence and release boundary

Gateway tests exercise the real send state machine and SQLite store against
synthetic provider peers: tenant-local discovery, successful replay, changed
payload denial, membership/provider/posting denials, partial-send ambiguity,
and durable in-flight recovery. Python tests cover configured/native grants,
company/source/revocation/parent guards and independent child scheduling.
They are not proof of live WhatsApp delivery or a full native browser session.
Real Frappe CI additionally requires a disabled original company mapping to
survive repeated migrations. Enabled-setting, native end-to-end document and
report delivery/worker/permission/browser acceptance remains required before
this draft can be released and consumed. Do not label that proof PASS from
the source contracts or provider-peer tests.

Fresh-site setup prepares the installed ERPNext Setup Wizard's Warehouse Type
presets before inserting its synthetic Company. A bench install alone does not
create those prerequisites; native Company warehouse creation otherwise fails
with `Could not find Warehouse Type: Transit`. This preparation is restricted to
`integration.local`, reuses existing prerequisites, does not run the global
wizard, and retains native Company/link validation. Setup errors roll back
instead of committing a partial preservation fixture. Focused tests cover the
ordering, reuse, production-site refusal and error paths; passing those tests
does not replace actual installation and both migrations in CI.

No app version bump, signed tag, image or release is created by this feature PR.
After review and required CI, use the normal signed immutable release process.
Consumers must import the verified release/source/gateway identity through
their normal dependency updater; never patch the frozen vendor mirror.
