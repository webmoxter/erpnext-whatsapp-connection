import frappe
from frappe import _
from frappe.model.document import Document


class ERPNextWhatsAppDeliveryHistory(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if before and (before.get('recipient_type') == 'Group' or self.get('recipient_type') == 'Group'
                       or before.get('copy_of') or self.get('copy_of')):
            for field in ('company', 'owner', 'provider', 'reference_type', 'reference_doctype',
                          'reference_name', 'report_name', 'report_filters', 'source_modified',
                          'pdf_file', 'pdf_sha256', 'message_text', 'print_format', 'message_template',
                          'copy_of', 'recipient_type', 'recipient', 'idempotency_key'):
                if self.get(field) != before.get(field):
                    frappe.throw(_('Queued group copy identity and content are immutable.'))
        if (
            self.status in {"Submitted to WhatsApp", "Acknowledged by WhatsApp"}
            and not self.provider_message_ids
        ):
            frappe.throw(_("A submitted WhatsApp record must contain a provider message ID."))
        if self.reference_type == "Document" and (not self.reference_doctype or not self.reference_name):
            frappe.throw(_("A document delivery must retain its document reference."))
        if self.reference_type == "Report" and not self.report_name:
            frappe.throw(_("A report delivery must retain its report reference."))
