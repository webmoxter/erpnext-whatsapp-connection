import base64

import frappe
from frappe import _

from erpnext_whatsapp_connection.gateway_client import WhatsAppGatewayError, gateway_request, site_payload
from erpnext_whatsapp_connection.permissions import is_manager


def _require_manager():
    if frappe.session.user == "Guest" or not is_manager():
        frappe.throw(_("Only a WhatsApp manager can manage the connection."), frappe.PermissionError)


def _settings():
    return frappe.get_single("ERPNext WhatsApp Settings")


def _gateway_provider(provider: str) -> str:
    return "Official API" if provider == "Official API" else "Baileys"


def _update_status(result: dict):
    values = {
        "connection_status": result.get("status") or "Disconnected",
        "last_error": result.get("last_error") or "",
        "last_connected_at": result.get("last_connected_at") or None,
        "last_disconnected_at": result.get("last_disconnected_at") or None,
    }
    for field, value in values.items():
        frappe.db.set_single_value("ERPNext WhatsApp Settings", field, value, update_modified=False)


@frappe.whitelist()
def get_status():
    _require_manager()
    settings = _settings()
    try:
        result = gateway_request(
            "/v1/status", site_payload(provider=_gateway_provider(settings.provider))
        )
    except WhatsAppGatewayError as exc:
        result = {
            "provider": settings.provider,
            "status": "Error",
            "connected": False,
            "authenticated": False,
            "qr_data_url": "",
            "last_error": str(exc),
        }
    _update_status(result)
    return result


@frappe.whitelist(methods=["POST"])
def connect():
    _require_manager()
    settings = _settings()
    result = gateway_request(
        "/v1/connect", site_payload(provider=_gateway_provider(settings.provider)), timeout=75
    )
    _update_status(result)
    return result


@frappe.whitelist(methods=["POST"])
def disconnect_and_remove_authentication():
    _require_manager()
    settings = _settings()
    result = gateway_request(
        "/v1/disconnect", site_payload(provider=_gateway_provider(settings.provider)), timeout=30
    )
    _update_status(result)
    return result


@frappe.whitelist(methods=["POST"])
def configure_official_api(
    access_token: str,
    phone_number_id: str,
    business_account_id: str = "",
    api_version: str = "v26.0",
    app_secret: str = "",
    verify_token: str = "",
):
    _require_manager()
    if not access_token or not phone_number_id or not app_secret or not verify_token:
        frappe.throw(_("The access token, phone number ID, app secret and webhook token are required."))
    result = gateway_request(
        "/v1/cloud/configure",
        site_payload(
            access_token=access_token,
            phone_number_id=phone_number_id,
            business_account_id=business_account_id,
            api_version=api_version,
            app_secret=app_secret,
            verify_token=verify_token,
        ),
        timeout=75,
    )
    settings = _settings()
    settings.provider = "Official API"
    settings.official_phone_number_id = phone_number_id
    settings.official_business_account_id = business_account_id
    settings.official_api_version = api_version
    settings.webhook_url = (
        f"https://{frappe.local.site}/api/method/erpnext_whatsapp_connection.settings_api.cloud_webhook"
    )
    settings.save(ignore_permissions=True)
    _update_status(result)
    return result


@frappe.whitelist(allow_guest=True)
def cloud_webhook():
    tenant_id = frappe.local.site
    if frappe.request.method == "GET":
        if frappe.form_dict.get("hub.mode") != "subscribe":
            frappe.throw(_("Unsupported webhook verification mode."), frappe.PermissionError)
        result = gateway_request(
            "/v1/cloud/webhook/verify",
            site_payload(
                verify_token=frappe.form_dict.get("hub.verify_token"),
                challenge=frappe.form_dict.get("hub.challenge"),
            ),
        )
        frappe.response["type"] = "txt"
        frappe.response["message"] = result.get("challenge") or ""
        return
    raw = frappe.request.get_data(cache=True)
    gateway_request(
        "/v1/cloud/webhook",
        {
            "tenant_id": tenant_id,
            "payload_base64": base64.b64encode(raw).decode(),
            "signature": frappe.get_request_header("X-Hub-Signature-256") or "",
        },
    )
    return {"success": True}
