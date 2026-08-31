import frappe


MANAGER_ROLES = {"System Manager", "ERPNext WhatsApp Manager"}
SENDER_ROLE = "ERPNext WhatsApp Sender"


def is_manager(user: str | None = None) -> bool:
    return bool(MANAGER_ROLES.intersection(frappe.get_roles(user)))


def can_send(user: str | None = None) -> bool:
    return is_manager(user) or SENDER_ROLE in frappe.get_roles(user)


def require_sender() -> None:
    if frappe.session.user == "Guest" or not can_send():
        frappe.throw("You do not have permission to send documents by WhatsApp.", frappe.PermissionError)


def outbound_message_query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    if is_manager(user):
        return ""
    if SENDER_ROLE in frappe.get_roles(user):
        return f"`tabERPNext WhatsApp Delivery History`.`owner` = {frappe.db.escape(user)}"
    return "1=0"


def outbound_message_has_permission(doc, user=None, permission_type=None):
    user = user or frappe.session.user
    if is_manager(user):
        return True
    return SENDER_ROLE in frappe.get_roles(user) and doc.owner == user
