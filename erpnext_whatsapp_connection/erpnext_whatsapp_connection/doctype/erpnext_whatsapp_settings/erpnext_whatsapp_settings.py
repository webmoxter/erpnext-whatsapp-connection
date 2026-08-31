import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class ERPNextWhatsAppSettings(Document):
    def validate(self):
        if self.provider not in {"Linked Device", "Official API"}:
            frappe.throw(_("Select a supported WhatsApp provider."))
        self.throttle_seconds = max(10, min(300, cint(self.throttle_seconds or 10)))
        self.maximum_retries = max(0, min(5, cint(self.maximum_retries or 3)))
