import frappe
from frappe import _
from frappe.model.document import Document


class ERPNextWhatsAppMessageTemplate(Document):
    def validate(self):
        if self.reference_type == "Document" and not self.document_type:
            frappe.throw(_("Document Type is required for a document template."))
        if self.reference_type == "Report" and not self.report_name:
            frappe.throw(_("Report is required for a report template."))
        if self.reference_type == "Document":
            self.report_name = None
        else:
            self.document_type = None
        if self.is_default and self.enabled:
            filters = {
                "enabled": 1,
                "is_default": 1,
                "reference_type": self.reference_type,
                "document_type": self.document_type or "",
                "report_name": self.report_name or "",
                "company": self.company or "",
                "name": ("!=", self.name or ""),
            }
            if frappe.db.exists(self.doctype, filters):
                frappe.throw(_("Only one default template is allowed for this target and company."))
