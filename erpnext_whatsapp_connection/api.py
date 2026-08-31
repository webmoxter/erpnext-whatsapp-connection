from __future__ import annotations

import hashlib
import json
import re
from html import escape

import frappe
from frappe import _
from frappe.utils import cint, fmt_money, now_datetime
from frappe.utils.file_manager import save_file
from frappe.utils.pdf import get_pdf

from erpnext_whatsapp_connection.adapters import document_adapter, report_adapter
from erpnext_whatsapp_connection.permissions import require_sender


HISTORY_DOCTYPE = "ERPNext WhatsApp Delivery History"
TEMPLATE_DOCTYPE = "ERPNext WhatsApp Message Template"


def _settings():
    settings = frappe.get_single("ERPNext WhatsApp Settings")
    if not settings.enabled:
        frappe.throw(_("Enable the WhatsApp transport before sending."))
    return settings


def _normalize_number(value: str) -> str:
    digits = re.sub(r"[\s()+.\-]", "", str(value or "").strip())
    if digits.startswith("00"):
        digits = digits[2:]
    if not re.fullmatch(r"[1-9]\d{7,14}", digits):
        frappe.throw(_("Enter a valid international WhatsApp number including the country code."))
    return f"+{digits}"


def _add_number(result: list[dict], seen: set[str], value, source: str):
    if not value:
        return
    try:
        number = _normalize_number(value)
    except frappe.ValidationError:
        return
    if number not in seen:
        seen.add(number)
        result.append({"value": number, "label": f"{number} — {source}"})


def _customer_numbers(customer_name: str) -> list[dict]:
    customer = frappe.get_doc("Customer", customer_name)
    customer.check_permission("read")
    result, seen = [], set()
    for fieldname in ("mobile_no", "phone", "phone_no"):
        if customer.meta.has_field(fieldname):
            _add_number(result, seen, customer.get(fieldname), _("Customer"))

    contact_names = []
    if customer.meta.has_field("customer_primary_contact") and customer.customer_primary_contact:
        contact_names.append(customer.customer_primary_contact)
    contact_names.extend(
        frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": customer.name,
                "parenttype": "Contact",
            },
            pluck="parent",
        )
    )
    for contact_name in dict.fromkeys(contact_names):
        contact = frappe.get_doc("Contact", contact_name)
        if not contact.has_permission("read"):
            continue
        _add_number(result, seen, contact.mobile_no, _("Contact {0}").format(contact.full_name))
        _add_number(result, seen, contact.phone, _("Contact {0}").format(contact.full_name))
        for row in contact.get("phone_nos") or []:
            _add_number(result, seen, row.phone, _("Contact {0}").format(contact.full_name))

    if customer.meta.has_field("customer_primary_address") and customer.customer_primary_address:
        address = frappe.get_doc("Address", customer.customer_primary_address)
        if address.has_permission("read"):
            _add_number(result, seen, address.phone, _("Customer Address"))
    return result


def _validate_document(doctype: str, name: str):
    adapter = document_adapter(doctype)
    if not adapter:
        frappe.throw(_("WhatsApp sending is not registered for {0}.").format(doctype))
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    if not frappe.has_permission(doctype, ptype="print", doc=doc):
        frappe.throw(_("You do not have permission to print this document."), frappe.PermissionError)
    for fieldname, required in (adapter.get("required_values") or {}).items():
        if doc.get(fieldname) != required:
            frappe.throw(_("This document is not an eligible customer receipt."))
    party_type_field = adapter.get("party_type_field")
    if party_type_field and doc.get(party_type_field) != adapter.get("required_party_type"):
        frappe.throw(_("Only customer documents may be sent through this action."))
    settings = _settings()
    if (
        cint(settings.require_submitted_documents)
        and adapter.get("require_submitted")
        and doc.meta.is_submittable
        and doc.docstatus != 1
    ):
        frappe.throw(_("Submit the document before sending it by WhatsApp."))
    return doc, adapter


def _document_context(doc, adapter: dict) -> dict:
    party_name = doc.get(adapter.get("party_name_field")) or doc.get(adapter["party_field"])
    amount = doc.get(adapter.get("amount_field")) or 0
    currency = doc.get(adapter.get("currency_field")) or ""
    context = {
        "name": doc.name,
        "doctype": doc.doctype,
        "party_name": party_name,
        "customer": doc.get(adapter["party_field"]),
        "company": doc.get(adapter.get("company_field")) or "",
        "date": doc.get(adapter.get("date_field")) or "",
        "amount": amount,
        "currency": currency,
        "formatted_amount": fmt_money(amount, currency=currency),
        "doc": doc.as_dict(),
    }
    return context


def _template_rows(reference_type: str, target: str, company: str, fallback: str) -> list[dict]:
    target_field = "document_type" if reference_type == "Document" else "report_name"
    rows = frappe.get_all(
        TEMPLATE_DOCTYPE,
        filters={"enabled": 1, "reference_type": reference_type, target_field: target},
        fields=["name", "template_name", "company", "is_default", "message_template"],
        order_by="is_default desc, template_name asc",
    )
    rows = [row for row in rows if not row.company or row.company == company]
    if not rows:
        rows = [
            frappe._dict(
                name="",
                template_name=_("System Default"),
                company="",
                is_default=1,
                message_template=fallback,
            )
        ]
    return rows


def _render_templates(rows: list[dict], context: dict) -> list[dict]:
    rendered = []
    for row in rows:
        rendered.append(
            {
                "name": row.name,
                "label": row.template_name,
                "is_default": cint(row.is_default),
                "message": frappe.render_template(row.message_template, context),
            }
        )
    return rendered


def _validate_selected_template(
    reference_type: str, target: str, company: str, template_name: str
) -> str | None:
    if not template_name:
        return None
    template = frappe.get_doc(TEMPLATE_DOCTYPE, template_name)
    template.check_permission("read")
    target_field = "document_type" if reference_type == "Document" else "report_name"
    if (
        not template.enabled
        or template.reference_type != reference_type
        or template.get(target_field) != target
        or (template.company and template.company != company)
    ):
        frappe.throw(_("Select an enabled WhatsApp template registered for this source."))
    return template.name


def _print_formats(doctype: str) -> list[str]:
    formats = ["Standard"]
    filters = {"doc_type": doctype}
    if frappe.get_meta("Print Format").has_field("disabled"):
        filters["disabled"] = 0
    formats.extend(
        frappe.get_all(
            "Print Format",
            filters=filters,
            pluck="name",
            order_by="name asc",
        )
    )
    return list(dict.fromkeys(formats))


def _validate_print_format(doctype: str, print_format: str) -> str:
    print_format = print_format or "Standard"
    if print_format not in _print_formats(doctype):
        frappe.throw(_("Select a print format registered for this document type."))
    return print_format


@frappe.whitelist()
def prepare_document(doctype: str, name: str):
    require_sender()
    doc, adapter = _validate_document(doctype, name)
    context = _document_context(doc, adapter)
    customer = doc.get(adapter["party_field"])
    numbers = _customer_numbers(customer)
    templates = _render_templates(
        _template_rows("Document", doctype, context["company"], adapter["default_message"]),
        context,
    )
    return {
        "recipients": numbers,
        "print_formats": _print_formats(doctype),
        "templates": templates,
        "source_modified": str(doc.modified),
        "title": f"{doctype} {name}",
    }


@frappe.whitelist()
def preview_document_pdf(doctype: str, name: str, print_format: str = "Standard"):
    require_sender()
    doc, _adapter = _validate_document(doctype, name)
    print_format = _validate_print_format(doctype, print_format)
    content = frappe.get_print(
        doctype,
        name,
        None if print_format == "Standard" else print_format,
        doc=doc,
        as_pdf=True,
        user=frappe.session.user,
    )
    frappe.local.response.filename = f"{name}.pdf".replace("/", "-")
    frappe.local.response.filecontent = content
    frappe.local.response.type = "pdf"


def _store_delivery(*, reference_type, recipient, message, pdf, filename, **values):
    settings = _settings()
    history = frappe.get_doc(
        {
            "doctype": HISTORY_DOCTYPE,
            "status": "Queued",
            "provider": settings.provider,
            "reference_type": reference_type,
            "recipient": recipient,
            "recipient_masked": f"********{recipient[-4:]}",
            "message_text": message,
            "queued_at": now_datetime(),
            "retry_count": 0,
            "max_retries": cint(settings.maximum_retries),
            "idempotency_key": f"wa:{frappe.local.site}:{frappe.generate_hash(length=48)}",
            **values,
        }
    ).insert(ignore_permissions=True)
    file_doc = save_file(filename, pdf, HISTORY_DOCTYPE, history.name, is_private=1)
    digest = hashlib.sha256(pdf).hexdigest()
    frappe.db.set_value(
        HISTORY_DOCTYPE,
        history.name,
        {"pdf_file": file_doc.name, "pdf_sha256": digest},
        update_modified=False,
    )
    frappe.enqueue(
        "erpnext_whatsapp_connection.outbound.process_outbound_message",
        queue="long",
        enqueue_after_commit=True,
        message_name=history.name,
        job_id=f"whatsapp:{history.name}",
    )
    return {"name": history.name, "status": history.status}


@frappe.whitelist(methods=["POST"])
def queue_document(
    doctype: str,
    name: str,
    recipient: str,
    print_format: str,
    message: str,
    source_modified: str,
    message_template: str = "",
):
    require_sender()
    doc, adapter = _validate_document(doctype, name)
    if str(doc.modified) != str(source_modified):
        frappe.throw(_("The document changed after preview. Refresh and review it again."))
    allowed_numbers = {row["value"] for row in _customer_numbers(doc.get(adapter["party_field"]))}
    recipient = _normalize_number(recipient)
    if recipient not in allowed_numbers:
        frappe.throw(_("Select a WhatsApp number linked to this customer."), frappe.PermissionError)
    message = str(message or "").strip()
    if not message or len(message) > 4096:
        frappe.throw(_("The message must contain 1 to 4096 characters."))
    print_format = _validate_print_format(doctype, print_format)
    message_template = _validate_selected_template(
        "Document", doctype, doc.get(adapter.get("company_field")) or "", message_template
    )
    pdf = frappe.get_print(
        doctype,
        name,
        None if print_format == "Standard" else print_format,
        doc=doc,
        as_pdf=True,
        user=frappe.session.user,
    )
    return _store_delivery(
        reference_type="Document",
        reference_doctype=doctype,
        reference_name=name,
        recipient=recipient,
        message=message,
        message_template=message_template,
        print_format=None if print_format == "Standard" else print_format,
        source_modified=doc.modified,
        pdf=pdf,
        filename=f"{doctype}-{name}.pdf".replace("/", "-"),
    )


def _validate_report(report_name: str, filters) -> tuple[dict, dict, str, str]:
    adapter = report_adapter(report_name)
    if not adapter:
        frappe.throw(_("WhatsApp sending is not registered for this report."))
    filters = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
    report = frappe.get_doc("Report", report_name)
    if not frappe.has_permission(report.ref_doctype, ptype="report"):
        frappe.throw(_("You do not have permission to run this report."), frappe.PermissionError)
    party_type_field = adapter.get("party_type_filter")
    if party_type_field and filters.get(party_type_field) != adapter.get("required_party_type"):
        frappe.throw(_("Select Customer as the party type before sending this report."))
    customer = filters.get(adapter["customer_filter"])
    if isinstance(customer, list):
        if len(customer) != 1:
            frappe.throw(_("Select exactly one customer before sending this report."))
        customer = customer[0]
    if not customer or not isinstance(customer, str):
        frappe.throw(_("Select exactly one customer before sending this report."))
    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.check_permission("read")
    company = filters.get(adapter.get("company_filter")) or ""
    return adapter, filters, customer, company


def _report_pdf(report_name: str, filters: dict) -> bytes:
    from frappe.desk.query_report import run

    result = run(report_name, filters=filters, ignore_prepared_report=True)
    columns = result.get("columns") or []
    rows = result.get("result") or []
    if len(rows) > 5000:
        frappe.throw(_("Narrow the report filters to 5,000 rows or fewer before sending."))
    normalized_columns = []
    for index, column in enumerate(columns):
        if isinstance(column, str):
            parts = column.split(":", 1)
            normalized_columns.append({"label": parts[0], "fieldname": f"column_{index}"})
        else:
            normalized_columns.append(column)
    labels = [column.get("label") or column.get("fieldname") for column in normalized_columns]
    fields = [column.get("fieldname") for column in normalized_columns]
    head = "".join(f"<th>{escape(str(label or ''))}</th>" for label in labels)
    body = []
    for row in rows:
        values = row if isinstance(row, dict) else dict(zip(fields, row))
        body.append(
            "<tr>" + "".join(f"<td>{escape(str(values.get(field) or ''))}</td>" for field in fields) + "</tr>"
        )
    filter_text = escape(json.dumps(filters, ensure_ascii=False, sort_keys=True, default=str))
    html = (
        "<html><head><style>body{font-family:sans-serif;font-size:9pt}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:4px}"
        "th{background:#eee}</style></head><body>"
        f"<h2>{escape(report_name)}</h2><p>{filter_text}</p><table><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></body></html>"
    )
    return get_pdf(html, {"orientation": "Landscape"})


@frappe.whitelist()
def prepare_report(report_name: str, filters=None):
    require_sender()
    _settings()
    adapter, filters, customer, company = _validate_report(report_name, filters)
    customer_doc = frappe.get_doc("Customer", customer)
    context = {
        "party_name": customer_doc.customer_name,
        "customer": customer,
        "company": company,
        "filters": filters,
    }
    return {
        "recipients": _customer_numbers(customer),
        "templates": _render_templates(
            _template_rows("Report", report_name, company, adapter["default_message"]), context
        ),
        "filters": filters,
        "title": report_name,
    }


@frappe.whitelist()
def preview_report_pdf(report_name: str, filters=None):
    require_sender()
    _settings()
    _adapter, filters, _customer, _company = _validate_report(report_name, filters)
    content = _report_pdf(report_name, filters)
    frappe.local.response.filename = f"{report_name}.pdf".replace("/", "-")
    frappe.local.response.filecontent = content
    frappe.local.response.type = "pdf"


@frappe.whitelist(methods=["POST"])
def queue_report(report_name: str, filters, recipient: str, message: str, message_template: str = ""):
    require_sender()
    _settings()
    _adapter, filters, customer, company = _validate_report(report_name, filters)
    allowed_numbers = {row["value"] for row in _customer_numbers(customer)}
    recipient = _normalize_number(recipient)
    if recipient not in allowed_numbers:
        frappe.throw(_("Select a WhatsApp number linked to this customer."), frappe.PermissionError)
    message = str(message or "").strip()
    if not message or len(message) > 4096:
        frappe.throw(_("The message must contain 1 to 4096 characters."))
    message_template = _validate_selected_template(
        "Report", report_name, company, message_template
    )
    pdf = _report_pdf(report_name, filters)
    return _store_delivery(
        reference_type="Report",
        report_name=report_name,
        report_filters=json.dumps(filters, separators=(",", ":"), ensure_ascii=False, default=str),
        recipient=recipient,
        message=message,
        message_template=message_template,
        pdf=pdf,
        filename=f"{report_name}.pdf".replace("/", "-"),
    )
