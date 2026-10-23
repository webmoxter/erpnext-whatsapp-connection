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
Real Frappe CI requires a disabled original company mapping to survive repeated
migrations, followed by `group_acceptance.validate` on the explicitly enabled
disposable site. The latter exercises actual native enabled settings save and
reopen, a draft synthetic Sales Invoice and Accounts Receivable PDF, separate
private Files and history, real Redis/RQ primary/copy jobs, copy-only retry,
current sender/source revocation, forged group and foreign Company denial,
uncertain-outcome reconciliation, and two further migrations of enabled rules.
The actual shipped Settings page runs in Chromium with a custom native Settings
Write role; that grant is revoked while retaining the existing connector Manager
carrier. Sender business Read/Print/Report comes from a separate custom role;
the connector's existing Sender carrier remains independent. No System Manager
business grant or standard Report edit/export is used to make these tests work.
The disposable report-reader role also has Journal Entry Read: native Accounts
Receivable calls permission-checked `get_list` for journal-backed invoices even
on an empty ledger. Acceptance asserts this role has no Journal Entry
Create/Write/Submit/Cancel/Delete authority. This fixture grant changes no
production role, replaces no native permission check, and grants no connector
user access automatically.

Browser acceptance uses the real Save button with Chromium input events and
waits for the dialog/backdrop and native AJAX to finish. Calling `frm.save()`
directly from JavaScript does not establish a trusted user gesture: Frappe's
save-confirmation audio then produces an unhandled `NotAllowedError` in a fresh
browser profile. The fixture retains normal sound preferences, autoplay policy
and the uncaught-exception gate; it does not mute, suppress or allowlist that
failure. It also requires the add-on namespace functions to execute, rather
than treating a script tag as proof that its asset loaded. Chromium has an
explicit desktop viewport and an owned process group that is stopped before
its temporary profile is removed. No mobile-browser coverage is claimed.

If browser exceptions occur, diagnostics retain static script locations and
typed HTTP/exception identifiers only. Hosts, query strings, request/response
bodies, message text, credentials and record paths are excluded. Diagnostics
remain bounded and do not turn browser failures into success.

The native application uses its real signed Unix-HTTP client against a local
capture peer with an ephemeral key. This is isolated transport/protocol evidence,
not live Meta delivery. The real gateway state machine/SQLite provider-peer tests
remain independent. Mandatory typed evidence is checked by
`scripts/verify-native-group-evidence.py`; omitted, false, foreign-site or wrong-
version results fail the installation lane. The first enabled-group run failed
during synthetic Customer setup because its Customer Group was a group node.
The corrected fixture creates selectable leaf entries beneath the native
Customer Group, Territory and Item Group roots, without bypassing validation.
Authoritative acceptance remains pending until revised-head CI actually
completes; earlier green installation checks and source/unit tests do not
prove the new native stages.

The corrected full sequence passed on a fresh isolated local site with Frappe
16.31.0 / ERPNext 16.32.3, all typed evidence present, and 35 candidate source
files verified byte-for-byte. To fit a VFS-based Docker workspace, this local
reproduction imported the pinned image's exported filesystem as one temporary
layer. It is functional evidence, not certification of the original image
manifest: mandatory CI must still run the original pinned image digest. Neither
local nor CI protocol capture proves live Meta delivery or a consuming app's
separate runtime compatibility.

The draft invoice fixture explicitly creates its own enabled selling Price List
in the synthetic Company's currency and supplies native invoice/price-list
currency and conversion values. A fresh site has no selling defaults from the
Setup Wizard. No mandatory checks are disabled or business defaults changed.
Migrations also enqueue native search-index work on the long queue. The fixture
runs that owned work normally, then stops at the exact expected delivery/retry
job so the child can be inspected before it runs. Missing, foreign, failed or
excessive queued work fails acceptance; no queue is purged to force ordering.

Fresh-site setup prepares the installed ERPNext Setup Wizard's Warehouse Type
presets before inserting its synthetic Company. A bench install alone does not
create those prerequisites; native Company warehouse creation otherwise fails
with `Could not find Warehouse Type: Transit`. This preparation is restricted to
`integration.local`, reuses existing prerequisites, does not run the global
wizard, and retains native Company/link validation. Setup errors roll back
instead of committing a partial preservation fixture. Focused tests cover the
ordering, reuse, production-site refusal and error paths; passing those tests
does not replace actual installation and both migrations in CI.

The v0.1.5 preparation also derives the composer asset cache key from the source
version, checks native report admission and explicit Company Read before report
preparation, and displays uncertain-copy reconciliation separately from an
exhausted retry limit. The scheduler excludes reconciliation-required records.

Built-in report adapters use the pinned ERPNext v16 `party` filter, not the
obsolete `customer` alias: one-element lists for Accounts Receivable, Accounts
Receivable Summary and General Ledger; a single Link value for Customer Ledger
Summary. Reports that accept a party type require `Customer`. Empty, multiple or
forged customer selections fail before rendering. The native acceptance checks
that the validated Accounts Receivable customer becomes an actual native query
condition and remains in queued history. Its synthetic invoice stays draft:
this PDF/transport fixture does not prove posted financial balances. External
report adapters retain their declared filter field and may opt into the
`customer_filter_type` (`list` or `string`) normalization contract; missing type
retains the adapter's existing shape, and unknown types fail closed. No alias
is treated as authority for a different report filter.

After review and required CI, use the normal signed immutable release process.
Consumers must import the verified release/source/gateway identity through
their normal dependency updater; never patch the frozen vendor mirror.
