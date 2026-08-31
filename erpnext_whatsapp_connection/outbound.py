import base64
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from erpnext_whatsapp_connection.gateway_client import WhatsAppGatewayError, gateway_request, site_payload
from erpnext_whatsapp_connection.transports import send_delivery


HISTORY_DOCTYPE = "ERPNext WhatsApp Delivery History"
RETRY_DELAYS_SECONDS = (30, 120, 600)


def _pdf_payload(document) -> list[dict]:
    if not document.pdf_file:
        frappe.throw(_("The delivery record has no private PDF snapshot."))
    file_doc = frappe.get_doc("File", document.pdf_file)
    if file_doc.attached_to_doctype != HISTORY_DOCTYPE or file_doc.attached_to_name != document.name:
        frappe.throw(_("The PDF snapshot is not attached to this delivery record."))
    if not file_doc.is_private:
        frappe.throw(_("WhatsApp PDF snapshots must remain private."))
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    if hashlib.sha256(content).hexdigest() != document.pdf_sha256:
        frappe.throw(_("The PDF snapshot checksum does not match the delivery record."))
    if not content.startswith(b"%PDF-"):
        frappe.throw(_("The private attachment is not a PDF document."))
    return [{"filename": file_doc.file_name, "content_base64": base64.b64encode(content).decode()}]


def process_outbound_message(message_name: str):
    document = frappe.get_doc(HISTORY_DOCTYPE, message_name)
    if document.status in {"Submitted to WhatsApp", "Acknowledged by WhatsApp"}:
        return
    document.attempted_at = now_datetime()
    document.retry_count = cint(document.retry_count) + 1
    document.status = "Processing"
    document.save(ignore_permissions=True)
    try:
        settings = frappe.get_single("ERPNext WhatsApp Settings")
        if not settings.enabled:
            frappe.throw(_("The site's WhatsApp transport is disabled."))
        result = send_delivery(document=document, settings=settings, pdfs=_pdf_payload(document))
        document.status = "Submitted to WhatsApp"
        document.submitted_at = result.get("submitted_at")
        document.provider_message_ids = json.dumps(result.get("message_ids") or [])
        document.result_message = _("Submitted to WhatsApp")
        document.error_message = ""
        document.next_retry_at = None
    except Exception as exc:
        document.status = "Failed"
        document.error_message = str(exc)[:500]
        if cint(document.retry_count) <= cint(document.max_retries):
            delay = RETRY_DELAYS_SECONDS[
                min(cint(document.retry_count) - 1, len(RETRY_DELAYS_SECONDS) - 1)
            ]
            document.next_retry_at = add_to_date(now_datetime(), seconds=delay)
    document.save(ignore_permissions=True)


def retry_due_messages():
    names = frappe.get_all(
        HISTORY_DOCTYPE,
        filters={"status": "Failed", "next_retry_at": ("<=", now_datetime())},
        pluck="name",
        limit=50,
    )
    for name in names:
        frappe.enqueue(
            "erpnext_whatsapp_connection.outbound.process_outbound_message",
            queue="long",
            message_name=name,
            job_id=f"whatsapp-retry:{name}:{now_datetime().strftime('%Y%m%d%H%M')}",
        )


def sync_delivery_statuses():
    settings = frappe.get_single("ERPNext WhatsApp Settings")
    try:
        result = gateway_request("/v1/events", site_payload(after_id=cint(settings.last_event_id)))
    except WhatsAppGatewayError:
        return
    for event in result.get("events") or []:
        name = frappe.db.get_value(
            HISTORY_DOCTYPE, {"idempotency_key": event.get("idempotency_key")}, "name"
        )
        if name:
            values = {
                "status": event.get("status"),
                "result_message": event.get("message") or event.get("status"),
            }
            if event.get("status") == "Acknowledged by WhatsApp":
                values["acknowledged_at"] = event.get("created_at")
            frappe.db.set_value(HISTORY_DOCTYPE, name, values, update_modified=False)
        settings.last_event_id = max(cint(settings.last_event_id), cint(event.get("id")))
    if result.get("events"):
        settings.save(ignore_permissions=True)


def scheduled_maintenance():
    retry_due_messages()
    sync_delivery_statuses()
