import frappe

from erpnext_whatsapp_connection.install import after_migrate


REQUIRED_DOCTYPES = (
    "ERPNext WhatsApp Settings",
    "ERPNext WhatsApp Message Template",
    "ERPNext WhatsApp Delivery History",
)
REQUIRED_ROLES = ("ERPNext WhatsApp Manager", "ERPNext WhatsApp Sender")


def validate_installation():
    """Fail closed when a real installed site is missing the public contract."""
    after_migrate()
    after_migrate()
    for doctype in REQUIRED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(f"Missing installed DocType: {doctype}")
    for role in REQUIRED_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.throw(f"Missing installed role: {role}")
    if not frappe.db.exists(
        "ERPNext WhatsApp Message Template", "Default Sales Invoice"
    ):
        frappe.throw("Default Sales Invoice message template was not seeded")
    if frappe.db.count(
        "ERPNext WhatsApp Message Template", {"name": "Default Sales Invoice"}
    ) != 1:
        frappe.throw("Default Sales Invoice message template is not idempotent")
    frappe.get_single("ERPNext WhatsApp Settings")
    return {
        "app": "erpnext_whatsapp_connection",
        "doctypes": list(REQUIRED_DOCTYPES),
        "roles": list(REQUIRED_ROLES),
        "repeat_migration": "passed",
    }
