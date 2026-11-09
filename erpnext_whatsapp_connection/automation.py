"""Opt-in, consent-bound, per-company WhatsApp document automation.

This module proposes notifications on submitted customer documents.  It never
sends directly: approved requests reuse the add-on's durable PDF delivery queue.
There is deliberately no guest API, arbitrary DocType, or generic phone sender.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.exceptions import DuplicateEntryError
from frappe.utils import cint, now_datetime

from erpnext_whatsapp_connection import api
from erpnext_whatsapp_connection.permissions import is_manager


REQUEST = "ERPNext WhatsApp Automation Request"
SUPPORTED = frozenset({"Sales Invoice", "Payment Entry"})
OPT_IN = "erpnext_whatsapp_auto_opt_in"
AUTO_PHONE = "erpnext_whatsapp_auto_phone"
CONSENT_REFERENCE = "erpnext_whatsapp_auto_consent_reference"


class AutomationPolicyError(Exception):
    """Non-secret reason why a proposed notification cannot be sent."""


@contextmanager
def _acting_as(user: str):
    prior = frappe.session.user
    try:
        if not user or user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
            raise AutomationPolicyError("actor_disabled")
        frappe.set_user(user)
        yield
    finally:
        frappe.set_user(prior)


def _rule(settings, company: str, doctype: str):
    if not cint(settings.enabled) or not cint(settings.get("automation_enabled")):
        return None
    eligible = [
        row for row in settings.get("automation_rules") or []
        if cint(row.enabled) and row.company == company and row.document_type == doctype
    ]
    if len(eligible) > 1:
        raise AutomationPolicyError("ambiguous_company_rule")
    return eligible[0] if eligible else None


def _phone_digest(phone: str) -> str:
    return hashlib.sha256((frappe.local.site + "\x00" + phone).encode()).hexdigest()


def _render_message(doc, adapter, rule):
    context = api._document_context(doc, adapter)
    template_name = rule.message_template or ""
    source = adapter["default_message"]
    if template_name:
        row = frappe.get_doc(api.TEMPLATE_DOCTYPE, template_name)
        if (
            not cint(row.enabled)
            or row.reference_type != "Document"
            or row.document_type != doc.doctype
            or (row.company and row.company != doc.company)
        ):
            raise AutomationPolicyError("template_not_allowed")
        source = row.message_template
    message = frappe.render_template(source, context).strip()
    if not 1 <= len(message) <= 4096:
        raise AutomationPolicyError("message_not_valid")
    return message, template_name


def _prepare_payload(doctype: str, name: str, rule, actor: str, *, pdf: bool = False):
    with _acting_as(actor):
        doc, adapter = api._validate_document(doctype, name)
        if doctype not in SUPPORTED or doc.docstatus != 1:
            raise AutomationPolicyError("document_not_submitted")
        if not doc.company or doc.company != rule.company:
            raise AutomationPolicyError("company_changed")

        customer_name = doc.get(adapter["party_field"])
        customer = frappe.get_doc("Customer", customer_name)
        customer.check_permission("read")
        if not cint(customer.get(OPT_IN)) or not str(customer.get(CONSENT_REFERENCE) or "").strip():
            raise AutomationPolicyError("consent_missing")
        raw_phone = customer.get(AUTO_PHONE)
        if not raw_phone:
            raise AutomationPolicyError("recipient_not_configured")
        try:
            recipient = api._normalize_number(raw_phone)
        except Exception as exc:
            raise AutomationPolicyError("recipient_invalid") from exc
        allowed = {row["value"] for row in api._customer_numbers(customer_name)}
        if recipient not in allowed:
            raise AutomationPolicyError("recipient_not_linked_to_customer")

        print_format = rule.print_format or "Standard"
        api._validate_print_format(doctype, print_format)
        message, template_name = _render_message(doc, adapter, rule)
        result = {
            "document": doc,
            "customer": customer_name,
            "recipient": recipient,
            "message": message,
            "template_name": template_name,
            "print_format": print_format,
            "modified": str(doc.modified),
            "phone_digest": _phone_digest(recipient),
        }
        if pdf:
            result["pdf"] = frappe.get_print(
                doctype,
                name,
                None if print_format == "Standard" else print_format,
                doc=doc,
                as_pdf=True,
            )
            if not isinstance(result["pdf"], bytes) or not result["pdf"].startswith(b"%PDF-"):
                raise AutomationPolicyError("invalid_pdf")
        return result


def _request_key(doctype: str, name: str) -> str:
    data = "\x00".join((frappe.local.site, doctype, name, "on_submit"))
    return "WA-AUTO-" + hashlib.sha256(data.encode()).hexdigest()[:32]


def on_document_submit(doc, method=None):
    """Never interrupt an ERPNext submission for an optional notification."""
    if doc.doctype not in SUPPORTED or doc.docstatus != 1:
        return
    try:
        settings = frappe.get_single("ERPNext WhatsApp Settings")
        rule = _rule(settings, doc.company, doc.doctype)
        if not rule:
            return
        key = _request_key(doc.doctype, doc.name)
        if frappe.db.exists(REQUEST, key):
            return
        actor = frappe.session.user
        payload = _prepare_payload(doc.doctype, doc.name, rule, actor)
        mode = rule.delivery_mode or "Approval Required"
        if mode not in {"Approval Required", "Send Automatically"}:
            raise AutomationPolicyError("invalid_delivery_mode")
        frappe.get_doc({
            "doctype": REQUEST,
            "automation_key": key,
            "status": "Pending Approval" if mode == "Approval Required" else "Approved",
            "company": doc.company,
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "customer": payload["customer"],
            "recipient_masked": "********" + payload["recipient"][-4:],
            "phone_digest": payload["phone_digest"],
            "source_modified": payload["modified"],
            "source_event": "Submitted",
            "rule_name": rule.name,
            "delivery_mode": mode,
            "message_preview": payload["message"],
            "print_format": payload["print_format"],
            "template_name": payload["template_name"],
            "requested_by": actor,
        }).insert(ignore_permissions=True)

        if mode == "Send Automatically":
            _enqueue_dispatch(key, after_commit=True)
    except DuplicateEntryError:
        # A concurrent submission has already created the deterministic request.
        return
    except AutomationPolicyError:
        # Lack of consent, an invalid contact, or a disabled rule never blocks the
        # original financial document or becomes an unauthorized send.
        return
    except Exception as exc:
        frappe.log_error(
            "Optional WhatsApp automation submission error (" + type(exc).__name__ + ")",
            "WhatsApp automation",
        )


def _require_reviewer():
    if frappe.session.user == "Guest" or not is_manager():
        frappe.throw(_("A WhatsApp manager must approve automatic notifications."), frappe.PermissionError)


def _locked_request(name: str):
    # Serializes competing approve/deny/dispatch attempts for this site record.
    rows = frappe.db.sql(
        "SELECT name FROM `tabERPNext WhatsApp Automation Request` WHERE name = %s FOR UPDATE",
        (name,), as_dict=True,
    )
    if not rows:
        frappe.throw(_("Automation request not found."), frappe.DoesNotExistError)
    return frappe.get_doc(REQUEST, name)


def _current_rule(request):
    settings = frappe.get_single("ERPNext WhatsApp Settings")
    rule = _rule(settings, request.company, request.reference_doctype)
    if not rule or rule.name != request.rule_name or rule.delivery_mode != request.delivery_mode:
        raise AutomationPolicyError("automation_policy_changed")
    return rule


def _validate_request(request, actor: str, *, pdf: bool = False):
    rule = _current_rule(request)
    payload = _prepare_payload(
        request.reference_doctype, request.reference_name, rule, actor, pdf=pdf
    )
    if (
        payload["customer"] != request.customer
        or payload["modified"] != str(request.source_modified)
        or payload["phone_digest"] != request.phone_digest
        or payload["message"] != request.message_preview
        or payload["print_format"] != request.print_format
        or payload["template_name"] != (request.template_name or "")
    ):
        raise AutomationPolicyError("approved_content_changed")
    return payload


def _enqueue_dispatch(request_name: str, *, after_commit: bool):
    frappe.enqueue(
        "erpnext_whatsapp_connection.automation.dispatch_approved",
        queue="long",
        enqueue_after_commit=after_commit,
        job_id="whatsapp-automation:" + request_name,
        deduplicate=True,
        request_name=request_name,
    )


@frappe.whitelist(methods=["POST"])
def approve_request(request_name: str):
    _require_reviewer()
    request = _locked_request(request_name)
    if request.status != "Pending Approval" or request.delivery_mode != "Approval Required":
        frappe.throw(_("Only pending approval requests may be approved."))
    # Both the submitting user and the reviewer must retain relevant document
    # permissions and the customer must still have explicit consent.
    _validate_request(request, request.requested_by)
    _validate_request(request, frappe.session.user)
    request.status = "Approved"
    request.approved_by = frappe.session.user
    request.approved_at = now_datetime()
    request.save(ignore_permissions=True)
    _enqueue_dispatch(request.name, after_commit=True)
    return {"status": request.status, "name": request.name}


@frappe.whitelist(methods=["POST"])
def reject_request(request_name: str):
    _require_reviewer()
    request = _locked_request(request_name)
    if request.status != "Pending Approval":
        frappe.throw(_("Only pending approval requests may be rejected."))
    request.status = "Rejected"
    request.failure_reason = "rejected_by_manager"
    request.save(ignore_permissions=True)
    return {"status": request.status, "name": request.name}


def dispatch_approved(request_name: str):
    """Run inside Frappe's long queue; repeat calls are idempotent."""
    request = _locked_request(request_name)
    if request.status != "Approved" or request.delivery_history:
        return
    try:
        if request.delivery_mode == "Approval Required":
            if not request.approved_by or not is_manager(request.approved_by):
                raise AutomationPolicyError("reviewer_no_longer_authorized")
            # Verify both the originator and the reviewer, then render under
            # the reviewer's current document permissions.
            _validate_request(request, request.requested_by)
            actor = request.approved_by
        else:
            actor = request.requested_by
        payload = _validate_request(request, actor, pdf=True)
        with _acting_as(actor):
            # Disable automatic group copies. Company group rules remain intact
            # for manually approved sends; automation never expands recipients.
            delivery = api._store_delivery(
                reference_type="Document",
                company=request.company,
                reference_doctype=request.reference_doctype,
                reference_name=request.reference_name,
                recipient=payload["recipient"],
                message=payload["message"],
                message_template=payload["template_name"],
                print_format=None if payload["print_format"] == "Standard" else payload["print_format"],
                source_modified=payload["document"].modified,
                pdf=payload["pdf"],
                filename=(request.reference_doctype + "-" + request.reference_name + ".pdf").replace("/", "-"),
                include_group_copy=False,
            )
        request.status = "Queued"
        request.delivery_history = delivery["name"]
        request.save(ignore_permissions=True)
    except AutomationPolicyError as exc:
        request.status = "Blocked"
        request.failure_reason = str(exc)
        request.save(ignore_permissions=True)
    except Exception as exc:
        # Do not persist recipients, message content or underlying provider
        # diagnostics. Unexpected errors need operator review, not blind replay.
        frappe.log_error(
            "WhatsApp automation dispatch error (" + type(exc).__name__ + ")",
            "WhatsApp automation",
        )
        request.status = "Blocked"
        request.failure_reason = "unexpected_dispatch_failure"
        request.save(ignore_permissions=True)


def recover_approved_requests():
    """Recovery for committed requests whose after-commit enqueue was lost."""
    for row in frappe.get_all(
        REQUEST, filters={"status": "Approved"}, fields=["name"], limit=25
    ):
        _enqueue_dispatch(row.name, after_commit=False)
