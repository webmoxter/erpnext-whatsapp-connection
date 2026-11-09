import frappe

from erpnext_whatsapp_connection.adapters import DEFAULT_DOCUMENT_ADAPTERS, DEFAULT_REPORT_ADAPTERS


ROLES = ("ERPNext WhatsApp Manager", "ERPNext WhatsApp Sender")


def _ensure_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )


def _ensure_default_templates():
    doctype = "ERPNext WhatsApp Message Template"
    if not frappe.db.exists("DocType", doctype):
        return
    for target, adapter in DEFAULT_DOCUMENT_ADAPTERS.items():
        name = f"Default {target}"
        if not frappe.db.exists(doctype, name):
            frappe.get_doc(
                {
                    "doctype": doctype,
                    "template_name": name,
                    "enabled": 1,
                    "is_default": 1,
                    "reference_type": "Document",
                    "document_type": target,
                    "message_template": adapter["default_message"],
                }
            ).insert(ignore_permissions=True)
    for target, adapter in DEFAULT_REPORT_ADAPTERS.items():
        name = f"Default {target}"
        if not frappe.db.exists(doctype, name):
            frappe.get_doc(
                {
                    "doctype": doctype,
                    "template_name": name,
                    "enabled": 1,
                    "is_default": 1,
                    "reference_type": "Report",
                    "report_name": target,
                    "message_template": adapter["default_message"],
                }
            ).insert(ignore_permissions=True)


def _ensure_customer_automation_consent_fields():
    """Create opt-in fields without overwriting an existing Customer policy."""
    if not frappe.db.exists("DocType", "Customer"):
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {"Customer": [
            {
                "fieldname": "erpnext_whatsapp_auto_opt_in",
                "label": "Automatic WhatsApp Documents: Customer Opt-in Confirmed",
                "fieldtype": "Check",
                "default": "0",
                "insert_after": "customer_name",
                "description": "Enable only after recording the customer's explicit consent; manual sends are unaffected.",
            },
            {
                "fieldname": "erpnext_whatsapp_auto_phone",
                "label": "Automatic WhatsApp Recipient",
                "fieldtype": "Data",
                "insert_after": "erpnext_whatsapp_auto_opt_in",
                "description": "International number, also present on this Customer or a permitted linked Contact.",
            },
            {
                "fieldname": "erpnext_whatsapp_auto_consent_reference",
                "label": "WhatsApp Consent Evidence Reference",
                "fieldtype": "Data",
                "insert_after": "erpnext_whatsapp_auto_phone",
                "description": "Internal consent evidence identifier; do not paste personal messages here.",
            },
        ]},
        update=False,
    )


def after_install():
    _ensure_roles()
    _ensure_default_templates()
    _ensure_customer_automation_consent_fields()


def after_migrate():
    _ensure_roles()
    _ensure_default_templates()
    _ensure_customer_automation_consent_fields()
