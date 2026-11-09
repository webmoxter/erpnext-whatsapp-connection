import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ERPNextWhatsAppSettings(Document):
    def validate(self):
        if self.provider not in {"Linked Device", "Official API"}:
            frappe.throw(_("Select a supported WhatsApp provider."))
        self.throttle_seconds = max(10, min(300, cint(self.throttle_seconds or 10)))
        self.maximum_retries = max(0, min(5, cint(
            self.maximum_retries if self.maximum_retries is not None else 3)))
        from erpnext_whatsapp_connection.company_groups import validate_settings
        validate_settings(self)
        enabled = set()
        for row in self.get("automation_rules") or []:
            if row.document_type not in {"Sales Invoice", "Payment Entry"}:
                frappe.throw(_("Only submitted Sales Invoices and customer Payment Entries can be automated."))
            if row.delivery_mode not in {"Approval Required", "Send Automatically"}:
                frappe.throw(_("Choose a supported WhatsApp automation delivery mode."))
            if not row.company or not frappe.db.exists("Company", row.company):
                frappe.throw(_("Every automation rule requires an existing Company."))
            if row.print_format:
                from erpnext_whatsapp_connection.api import _validate_print_format
                _validate_print_format(row.document_type, row.print_format)
            if row.message_template:
                template = frappe.get_doc("ERPNext WhatsApp Message Template", row.message_template)
                if (not cint(template.enabled) or template.reference_type != "Document"
                    or template.document_type != row.document_type
                    or (template.company and template.company != row.company)):
                    frappe.throw(_("Automation template must match the document and company."))
            if cint(row.enabled):
                identity = (row.company, row.document_type)
                if identity in enabled:
                    frappe.throw(_("Only one enabled automation rule is allowed per company and document type."))
                enabled.add(identity)
