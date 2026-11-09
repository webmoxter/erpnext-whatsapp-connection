import frappe
from frappe.model.document import Document


class ERPNextWhatsAppAutomationRequest(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if not before:
            return
        immutable = (
            "automation_key", "company", "reference_doctype", "reference_name",
            "customer", "recipient_masked", "phone_digest", "source_modified",
            "source_event", "rule_name", "delivery_mode", "requested_by",
        )
        for field in immutable:
            if self.get(field) != before.get(field):
                frappe.throw("Automation request identity cannot be changed.")
        transitions = {
            "Pending Approval": {"Approved", "Rejected", "Blocked"},
            "Approved": {"Queued", "Blocked"},
            "Queued": set(), "Rejected": set(), "Blocked": set(),
        }
        if self.status != before.status and self.status not in transitions.get(before.status, set()):
            frappe.throw("Invalid automation request status transition.")
