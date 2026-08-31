import frappe
from frappe import _
from frappe.model.document import Document


class ERPNextWhatsAppDeliveryHistory(Document):
    def validate(self):
        if (
            self.status in {"Submitted to WhatsApp", "Acknowledged by WhatsApp"}
            and not self.provider_message_ids
        ):
            frappe.throw(_("A submitted WhatsApp record must contain a provider message ID."))
        if self.reference_type == "Document" and (not self.reference_doctype or not self.reference_name):
            frappe.throw(_("A document delivery must retain its document reference."))
        if self.reference_type == "Report" and not self.report_name:
            frappe.throw(_("A report delivery must retain its report reference."))
