from __future__ import annotations

from copy import deepcopy

import frappe


DEFAULT_DOCUMENT_ADAPTERS = {
    "Sales Invoice": {
        "party_type": "Customer",
        "party_field": "customer",
        "party_name_field": "customer_name",
        "company_field": "company",
        "date_field": "posting_date",
        "amount_field": "grand_total",
        "currency_field": "currency",
        "require_submitted": True,
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find Sales Invoice {{ name }} dated "
            "{{ date }} for {{ formatted_amount }}.\n\nRegards,\n{{ company }}"
        ),
    },
    "Payment Entry": {
        "party_type_field": "party_type",
        "required_party_type": "Customer",
        "required_values": {"payment_type": "Receive"},
        "party_field": "party",
        "party_name_field": "party_name",
        "company_field": "company",
        "date_field": "posting_date",
        "amount_field": "paid_amount",
        "currency_field": "paid_to_account_currency",
        "require_submitted": True,
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find Payment Receipt {{ name }} dated "
            "{{ date }} for {{ formatted_amount }}.\n\nRegards,\n{{ company }}"
        ),
    },
}

DEFAULT_REPORT_ADAPTERS = {
    "Accounts Receivable": {
        "customer_filter": "customer",
        "company_filter": "company",
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find your Accounts Receivable statement "
            "attached.\n\nRegards,\n{{ company }}"
        ),
    },
    "Accounts Receivable Summary": {
        "customer_filter": "customer",
        "company_filter": "company",
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find your receivable summary attached."
            "\n\nRegards,\n{{ company }}"
        ),
    },
    "Customer Ledger Summary": {
        "customer_filter": "customer",
        "company_filter": "company",
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find your customer statement attached."
            "\n\nRegards,\n{{ company }}"
        ),
    },
    "General Ledger": {
        "customer_filter": "party",
        "party_type_filter": "party_type",
        "required_party_type": "Customer",
        "company_filter": "company",
        "default_message": (
            "Dear {{ party_name }},\n\nPlease find your customer ledger attached."
            "\n\nRegards,\n{{ company }}"
        ),
    },
}


def _external_registry(hook_name: str) -> dict:
    registry = {}
    for dotted_path in frappe.get_hooks(hook_name) or []:
        values = frappe.get_attr(dotted_path)()
        if not isinstance(values, dict):
            raise TypeError(f"{dotted_path} must return a dictionary")
        registry.update(values)
    return registry


def document_adapters() -> dict:
    result = deepcopy(DEFAULT_DOCUMENT_ADAPTERS)
    result.update(_external_registry("erpnext_whatsapp_document_adapter_providers"))
    return result


def report_adapters() -> dict:
    result = deepcopy(DEFAULT_REPORT_ADAPTERS)
    result.update(_external_registry("erpnext_whatsapp_report_adapter_providers"))
    return result


def document_adapter(doctype: str) -> dict | None:
    return document_adapters().get(doctype)


def report_adapter(report_name: str) -> dict | None:
    return report_adapters().get(report_name)
