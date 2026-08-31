import hashlib
import hmac
import http.client
import json
import os
import secrets
import socket
import time

import frappe


SOCKET_PATH = os.environ.get(
    "ERPNEXT_WHATSAPP_SOCKET", "/run/erpnext-whatsapp/gateway.sock"
)
HMAC_KEY_FILE = os.environ.get(
    "ERPNEXT_WHATSAPP_HMAC_KEY_FILE", "/run/secrets/erpnext_whatsapp_gateway_hmac"
)


class WhatsAppGatewayError(RuntimeError):
    pass


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: int = 45):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _secret() -> bytes:
    try:
        with open(HMAC_KEY_FILE, "rb") as handle:
            value = handle.read().strip()
    except OSError as exc:
        raise WhatsAppGatewayError("The private WhatsApp gateway is not configured.") from exc
    if len(value) < 32:
        raise WhatsAppGatewayError("The private WhatsApp gateway authentication is invalid.")
    return value


def gateway_request(path: str, payload: dict, timeout: int = 60) -> dict:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{timestamp}\n{nonce}\nPOST\n{path}\n{body_hash}".encode()
    signature = hmac.new(_secret(), canonical, hashlib.sha256).hexdigest()
    connection = _UnixHTTPConnection(SOCKET_PATH, timeout=timeout)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-ERPNext-WhatsApp-Timestamp": timestamp,
                "X-ERPNext-WhatsApp-Nonce": nonce,
                "X-ERPNext-WhatsApp-Signature": signature,
            },
        )
        response = connection.getresponse()
        raw = response.read()
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise WhatsAppGatewayError("The private WhatsApp gateway is unavailable.") from exc
    finally:
        connection.close()
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise WhatsAppGatewayError("The private WhatsApp gateway returned an invalid response.") from exc
    if response.status >= 400:
        raise WhatsAppGatewayError(str(data.get("error") or "WhatsApp operation failed."))
    return data


def site_payload(**values) -> dict:
    return {"tenant_id": frappe.local.site, **values}
