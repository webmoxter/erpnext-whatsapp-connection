"""Read-only Pilot compatibility verification; never contacts WhatsApp."""

import frappe

from erpnext_whatsapp_connection import __version__


REQUIRED_DOCTYPES = (
    "ERPNext WhatsApp Settings",
    "ERPNext WhatsApp Message Template",
    "ERPNext WhatsApp Delivery History",
    "ERPNext WhatsApp Automation Rule",
    "ERPNext WhatsApp Automation Request",
)
CONSENT_FIELDS = (
    "erpnext_whatsapp_auto_opt_in",
    "erpnext_whatsapp_auto_phone",
    "erpnext_whatsapp_auto_consent_reference",
)


def verify_site():
    """Validate schema only, not gateway connectivity or actual message sending."""
    if not {"frappe", "erpnext", "erpnext_whatsapp_connection"} <= set(frappe.get_installed_apps()):
        frappe.throw("Frappe, ERPNext and WhatsApp add-on must all be installed.")
    if any(not frappe.db.exists("DocType", d) for d in REQUIRED_DOCTYPES):
        frappe.throw("Missing installed WhatsApp DocType.")
    if any(not frappe.get_meta("Customer").has_field(f) for f in CONSENT_FIELDS):
        frappe.throw("Missing Customer consent fields.")
    settings = frappe.get_single("ERPNext WhatsApp Settings")
    return {
        "addon": "erpnext_whatsapp_connection",
        "version": __version__,
        "frappe_version": frappe.__version__,
        "schema": "PASS",
        "automation_enabled": bool(settings.get("automation_enabled")),
        "enabled_company_rules": sum(
            1 for rule in settings.get("automation_rules") or [] if rule.enabled
        ),
        "private_gateway": "NOT TESTED",
        "live_delivery": "NOT TESTED",
    }
