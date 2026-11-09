from erpnext_whatsapp_connection import __version__

app_name = "erpnext_whatsapp_connection"
app_title = "ERPNext WhatsApp Connection by TNGSol.com"
app_publisher = "TNGSol.com"
app_description = "Permission-checked WhatsApp document delivery for Frappe and ERPNext"
app_email = "support@tngsol.com"
app_license = "GPL-3.0"
frappe_version = ">=16.0.0 <17.0.0"
required_apps = ["erpnext"]

app_include_js = f"/assets/erpnext_whatsapp_connection/js/send_by_whatsapp.js?v={__version__}"

doctype_js = {
    "Sales Invoice": "public/js/document_button.js",
    "Payment Entry": "public/js/document_button.js",
}

# Consent-bound automation is off until explicitly enabled on a tenant site.
# This never replaces the existing manual Send by WhatsApp actions.
doc_events = {
    "Sales Invoice": {"on_submit": "erpnext_whatsapp_connection.automation.on_document_submit"},
    "Payment Entry": {"on_submit": "erpnext_whatsapp_connection.automation.on_document_submit"},
    "Customer": {"validate": "erpnext_whatsapp_connection.automation.validate_customer_consent_changes"},
}

after_install = "erpnext_whatsapp_connection.install.after_install"
after_migrate = "erpnext_whatsapp_connection.install.after_migrate"

permission_query_conditions = {
    "ERPNext WhatsApp Delivery History": (
        "erpnext_whatsapp_connection.permissions.outbound_message_query_conditions"
    ),
}

has_permission = {
    "ERPNext WhatsApp Delivery History": (
        "erpnext_whatsapp_connection.permissions.outbound_message_has_permission"
    ),
}

scheduler_events = {
    "cron": {"*/1 * * * *": ["erpnext_whatsapp_connection.outbound.scheduled_maintenance"]},
}
