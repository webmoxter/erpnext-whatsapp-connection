from __future__ import annotations

from copy import deepcopy

import frappe

from erpnext_whatsapp_connection.gateway_client import gateway_request, site_payload


BUILTIN_TRANSPORTS = {
    "Linked Device": {
        "send": "erpnext_whatsapp_connection.transports.send_via_bundled_gateway",
        "gateway_provider": "Baileys",
    },
    "Official API": {
        "send": "erpnext_whatsapp_connection.transports.send_via_bundled_gateway",
        "gateway_provider": "Official API",
    },
}


def transport_registry() -> dict:
    """Return transports, allowing an installed app to replace a provider safely.

    A provider may replace an existing label, such as ``Official API``, but the
    settings DocType remains the authority for which provider a site selected.
    """
    registry = deepcopy(BUILTIN_TRANSPORTS)
    for dotted_path in frappe.get_hooks("erpnext_whatsapp_transport_adapter_providers") or []:
        values = frappe.get_attr(dotted_path)()
        if not isinstance(values, dict):
            raise TypeError(f"{dotted_path} must return a dictionary")
        registry.update(values)
    return registry


def get_transport(provider: str) -> dict:
    transport = transport_registry().get(provider)
    if not transport or not transport.get("send"):
        frappe.throw(f"WhatsApp transport {provider!r} is not registered.")
    return transport


def send_delivery(*, document, settings, pdfs: list[dict]) -> dict:
    transport = get_transport(document.provider)
    sender = frappe.get_attr(transport["send"])
    return sender(document=document, settings=settings, pdfs=pdfs, transport=transport)


def send_via_bundled_gateway(*, document, settings, pdfs: list[dict], transport: dict) -> dict:
    return gateway_request(
        "/v1/send",
        site_payload(
            provider=transport["gateway_provider"],
            recipient=document.get_password("recipient"),
            text=document.message_text or "",
            pdfs=pdfs,
            idempotency_key=document.idempotency_key,
            throttle_ms=max(10, min(300, int(settings.throttle_seconds or 0))) * 1000,
        ),
        timeout=180,
    )
