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


def after_install():
    _ensure_roles()
    _ensure_default_templates()


def after_migrate():
    _ensure_roles()
    _ensure_default_templates()
