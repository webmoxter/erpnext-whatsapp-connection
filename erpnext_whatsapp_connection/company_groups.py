"""Opt-in company copies; group destinations are configuration, never caller input."""
import re

import frappe
from frappe import _
from frappe.utils import cint

from erpnext_whatsapp_connection.gateway_client import gateway_request, site_payload

SETTINGS = 'ERPNext WhatsApp Settings'


def group_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{5,24}(?:-[0-9]{5,24})?@g\.us', value):
        frappe.throw(_('Select a valid joined WhatsApp group.'))
    return value


def joined_groups():
    result = gateway_request('/v1/groups', site_payload())
    groups = result.get('groups')
    if not isinstance(groups, list):
        frappe.throw(_('The gateway did not return a valid group list.'))
    return {group_id(row['id']): str(row.get('name') or '') for row in groups}


def _company(company):
    if not isinstance(company, str) or not company:
        frappe.throw(_('A group copy requires one explicit permitted company.'), frappe.PermissionError)
    frappe.get_doc('Company', company).check_permission('read')


@frappe.whitelist()
def list_groups(company):
    if not frappe.has_permission(SETTINGS, 'write'):
        frappe.throw(_('WhatsApp Settings Write permission is required.'), frappe.PermissionError)
    _company(company)
    if frappe.get_single(SETTINGS).provider != 'Linked Device':
        frappe.throw(_('Group copies require Linked Device transport.'))
    return [{'value': key, 'label': name or _('Unnamed group')} for key, name in joined_groups().items()]


def validate_settings(settings):
    def state(doc):
        return {row.company: (cint(row.enabled), row.group_id) for row in doc.get('company_groups') or []}
    rows = settings.get('company_groups') or []
    if len({row.company for row in rows}) != len(rows):
        frappe.throw(_('Configure at most one WhatsApp group per company.'))
    before = settings.get_doc_before_save()
    previous = state(before) if before else {}
    current = state(settings)
    changed = {company for company in previous.keys() | current.keys()
               if previous.get(company) != current.get(company)}
    for company in changed:
        _company(company)
    enabled = [row for row in rows if cint(row.enabled)]
    if enabled and settings.provider != 'Linked Device':
        frappe.throw(_('Disable group copies before selecting a transport without group support.'))
    if not changed:
        return
    groups = joined_groups() if enabled else {}
    for row in rows:
        group_id(row.group_id)
        if cint(row.enabled):
            if row.group_id not in groups:
                frappe.throw(_('Select a group currently joined by this site account.'))
            row.group_name = groups[row.group_id]


def configured_group(settings, company):
    matches = [row for row in settings.get('company_groups') or []
               if row.company == company and cint(row.enabled)]
    if not matches:
        return None
    if len(matches) != 1 or settings.provider != 'Linked Device':
        frappe.throw(_('The company group configuration requires reconciliation.'))
    _company(company)
    return group_id(matches[0].group_id)


def validate_copy(document, settings):
    """Recheck original actor/source, immutable parent and current company rule."""
    from erpnext_whatsapp_connection.api import _validate_document, _validate_print_format, _validate_report
    from erpnext_whatsapp_connection.permissions import require_sender

    parent = frappe.get_doc(document.doctype, document.copy_of)
    if parent.status not in {'Submitted to WhatsApp', 'Acknowledged by WhatsApp'}:
        return False
    if parent.get('recipient_type') == 'Group' or parent.get('copy_of'):
        frappe.throw(_('Group copies cannot be copied again.'))
    for field in ('owner', 'company', 'provider', 'reference_type', 'reference_doctype',
                  'reference_name', 'report_name', 'report_filters', 'source_modified', 'pdf_sha256',
                  'message_text', 'print_format', 'message_template'):
        if document.get(field) != parent.get(field):
            frappe.throw(_('Group copy differs from its original delivery.'))
    original = frappe.session.user
    try:
        if document.owner == 'Guest':
            frappe.throw(_('Guest cannot own a group delivery.'), frappe.PermissionError)
        if not frappe.db.get_value('User', document.owner, 'enabled'):
            frappe.throw(_('The original sender is disabled.'), frappe.PermissionError)
        frappe.set_user(document.owner)
        require_sender()
        if configured_group(settings, document.company) != document.get_password('recipient'):
            frappe.throw(_('The company group copy configuration changed.'), frappe.PermissionError)
        if document.reference_type == 'Document':
            source, adapter = _validate_document(document.reference_doctype, document.reference_name)
            if source.get(adapter.get('company_field')) != document.company or str(source.modified) != str(document.source_modified):
                frappe.throw(_('The source company or document version changed.'))
            _validate_print_format(document.reference_doctype, document.print_format or 'Standard')
        else:
            if not frappe.get_doc('Report', document.report_name).is_permitted():
                frappe.throw(_('The original sender no longer has access to this report.'), frappe.PermissionError)
            _adapter, _filters, _customer, company = _validate_report(document.report_name, document.report_filters)
            if company != document.company:
                frappe.throw(_('The report company changed.'))
        return True
    finally:
        frappe.set_user(original)


def release_waiting_copies(primary_name):
    """Independent child jobs cannot cause the successful primary to resend."""
    for name in frappe.get_all('ERPNext WhatsApp Delivery History',
            filters={'copy_of': primary_name, 'status': ('in', ['Waiting for Primary', 'Queued'])}, pluck='name'):
        frappe.db.set_value('ERPNext WhatsApp Delivery History', name, 'status', 'Queued', update_modified=False)
        frappe.enqueue('erpnext_whatsapp_connection.outbound.process_outbound_message', queue='long',
            enqueue_after_commit=True, message_name=name, job_id='whatsapp:' + name, deduplicate=True)
