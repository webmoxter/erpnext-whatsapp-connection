"""Native group-copy acceptance, exclusively on the disposable CI site.

The signed Unix-HTTP peer is local protocol capture, never WhatsApp delivery.
Native documents, permissions, private Files, Redis/RQ and migrations are real.
"""
import base64
from contextlib import contextmanager
from datetime import date
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
from socketserver import UnixStreamServer
import subprocess
import sys
import tempfile
import threading
import time

import frappe


SETTINGS = 'ERPNext WhatsApp Settings'
HISTORY = 'ERPNext WhatsApp Delivery History'
GROUP = '120000000000000000@g.us'
OTHER_GROUP = '120000000000000001@g.us'


def stage(name):
    print('WHATSAPP_NATIVE_GROUP_STAGE=' + name, flush=True)


def require_fixture_site():
    if frappe.local.site != 'integration.local' or not frappe.conf.get('whatsapp_integration_acceptance'):
        raise RuntimeError('Group acceptance requires the explicitly enabled disposable site')


class ProtocolPeer:
    def __init__(self, root):
        self.key = secrets.token_hex(32).encode()
        self.key_file = root / 'hmac'
        with open(os.open(self.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
            handle.write(self.key)
        self.socket = root / 'gateway.sock'
        self.nonces = set()
        self.deliveries = {}
        self.attempts = {}
        self.group_failures = 0
        self.uncertain = False
        peer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Never log payloads, recipients or authentication headers.

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                stamp = self.headers.get('X-ERPNext-WhatsApp-Timestamp', '')
                nonce = self.headers.get('X-ERPNext-WhatsApp-Nonce', '')
                canonical = f'{stamp}\n{nonce}\nPOST\n{self.path}\n{hashlib.sha256(body).hexdigest()}'.encode()
                signature = hmac.new(peer.key, canonical, hashlib.sha256).hexdigest()
                valid = (stamp.isdigit() and abs(time.time() - int(stamp)) < 120 and nonce
                         and nonce not in peer.nonces and hmac.compare_digest(signature,
                             self.headers.get('X-ERPNext-WhatsApp-Signature', '')))
                if not valid:
                    return self.reply(403, {'error':'Invalid local protocol authentication'})
                peer.nonces.add(nonce)
                payload = json.loads(body)
                if payload.get('tenant_id') != 'integration.local':
                    return self.reply(403, {'error':'Foreign fixture site'})
                if self.path == '/v1/groups':
                    return self.reply(200, {'groups':[{'id':GROUP, 'name':'Synthetic company group'},
                        {'id':OTHER_GROUP, 'name':'Synthetic other group'}]})
                if self.path == '/v1/status':
                    return self.reply(200, {'status':'Connected', 'connected':True})
                if self.path != '/v1/send':
                    return self.reply(404, {'error':'Unsupported capture endpoint'})
                key = payload['idempotency_key']
                peer.attempts[key] = peer.attempts.get(key, 0) + 1
                if payload.get('recipient_type') == 'Group' and peer.group_failures:
                    peer.group_failures -= 1
                    return self.reply(400, {'error':'Synthetic provider failure',
                        'reconciliation_required':peer.uncertain})
                for pdf in payload.get('pdfs') or []:
                    if not base64.b64decode(pdf['content_base64']).startswith(b'%PDF-'):
                        return self.reply(400, {'error':'Invalid fixture PDF'})
                if key in peer.deliveries and peer.deliveries[key] != payload:
                    return self.reply(409, {'error':'Changed fixture request identity'})
                peer.deliveries[key] = payload
                return self.reply(200, {'message_ids':['synthetic-confirmed-id'],
                    'submitted_at':'2026-01-01T00:00:00Z'})

            def reply(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = UnixStreamServer(str(self.socket), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('Owned protocol capture did not stop')


@contextmanager
def captured_gateway(peer):
    from erpnext_whatsapp_connection import gateway_client
    previous = (gateway_client.SOCKET_PATH, gateway_client.HMAC_KEY_FILE)
    keys = {'ERPNEXT_WHATSAPP_SOCKET':str(peer.socket),
            'ERPNEXT_WHATSAPP_HMAC_KEY_FILE':str(peer.key_file), 'CI':'1'}
    environment = {key:os.environ.get(key) for key in keys}
    try:
        os.environ.update(keys)
        gateway_client.SOCKET_PATH = str(peer.socket)
        gateway_client.HMAC_KEY_FILE = str(peer.key_file)
        yield
    finally:
        gateway_client.SOCKET_PATH, gateway_client.HMAC_KEY_FILE = previous
        for key, value in environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def worker_once():
    """Execute exactly one real Redis job through native execute_job in RQ."""
    require_fixture_site()
    from frappe.utils.background_jobs import get_queue
    from rq import Worker
    queue = get_queue('long')
    worker = Worker([queue], connection=queue.connection)
    worker.work(burst=True, max_jobs=1, logging_level='ERROR', with_scheduler=False)


def run_worker():
    require_fixture_site()
    frappe.db.commit()
    result = subprocess.run(['bench', '--site', 'integration.local', 'execute',
        'erpnext_whatsapp_connection.group_acceptance.worker_once'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, check=False)
    if result.returncode:
        # Raw tracebacks can include worker arguments; keep them out of CI logs.
        raise AssertionError('Native isolated RQ worker failed; exit=' + str(result.returncode))
    frappe.db.rollback()  # End the parent read snapshot before inspecting child commits.


def fixture_tree_leaf(doctype, field, parent_field, name):
    """Create a synthetic selectable leaf beneath the native tree root.

    ERPNext rejects a group node as a Customer's Customer Group. Keep native
    validation enabled and use leaves for all three business tree links.
    """
    require_fixture_site()
    from frappe.utils.nestedset import get_root_of
    root = get_root_of(doctype)
    if not root:
        root = frappe.get_doc({'doctype':doctype, field:name + ' Root',
            'is_group':1}).insert(ignore_permissions=True).name
    return frappe.get_doc({'doctype':doctype, field:name, parent_field:root,
        'is_group':0}).insert(ignore_permissions=True).name


def setup_documents():
    require_fixture_site()
    company = frappe.get_doc('Company', 'WhatsApp Fixture Company')
    other = frappe.get_doc({'doctype':'Company', 'company_name':'WhatsApp Other Fixture Company',
        'abbr':'WOF', 'default_currency':'USD', 'country':'United States'}).insert(ignore_permissions=True)
    leaves = {}
    for doctype, field, parent_field, name in (
            ('Customer Group','customer_group_name','parent_customer_group','WhatsApp Fixture Customers'),
            ('Territory','territory_name','parent_territory','WhatsApp Fixture Territory'),
            ('Item Group','item_group_name','parent_item_group','WhatsApp Fixture Items')):
        leaves[doctype] = fixture_tree_leaf(doctype, field, parent_field, name)
    if not frappe.db.exists('UOM', 'Unit'):
        frappe.get_doc({'doctype':'UOM', 'uom_name':'Unit'}).insert(ignore_permissions=True)
    today = date.today()
    if not frappe.db.exists('Fiscal Year', str(today.year)):
        frappe.get_doc({'doctype':'Fiscal Year', 'year':str(today.year),
            'year_start_date':date(today.year,1,1), 'year_end_date':date(today.year,12,31)}).insert(ignore_permissions=True)
    customer = frappe.get_doc({'doctype':'Customer', 'customer_name':'WhatsApp Synthetic Customer',
        'customer_type':'Company', 'customer_group':leaves['Customer Group'],
        'territory':leaves['Territory'], 'mobile_no':'+12025550123'}).insert(ignore_permissions=True)
    item = frappe.get_doc({'doctype':'Item', 'item_code':'WHATSAPP-FIXTURE-ITEM',
        'item_name':'Synthetic delivery fixture', 'item_group':leaves['Item Group'],
        'stock_uom':'Unit', 'is_stock_item':0}).insert(ignore_permissions=True)
    income = frappe.db.get_value('Account', {'company':company.name, 'account_type':'Income Account',
        'is_group':0}, 'name') or frappe.db.get_value('Account', {'company':company.name,
        'root_type':'Income', 'is_group':0}, 'name')
    invoice = frappe.get_doc({'doctype':'Sales Invoice', 'company':company.name, 'customer':customer.name,
        'posting_date':today, 'due_date':today, 'currency':'USD', 'debit_to':company.default_receivable_account,
        'items':[{'item_code':item.name, 'qty':1, 'rate':12.34, 'income_account':income,
                  'cost_center':company.cost_center}]}).insert(ignore_permissions=True)
    role = frappe.get_doc({'doctype':'Role', 'role_name':'Synthetic company report reader',
        'desk_access':1}).insert(ignore_permissions=True)
    from frappe.permissions import add_permission
    for target in ('Company','Customer','Sales Invoice','Account','GL Entry'):
        name = add_permission(target, role.name, ptype='read')
        permission = frappe.get_doc('Custom DocPerm', name)
        permission.print = 1
        permission.report = 1
        permission.save(ignore_permissions=True)
        frappe.clear_cache(doctype=target)
    report = frappe.get_doc('Report', 'Accounts Receivable')
    # Native site customization, without editing/exporting a standard Report.
    frappe.get_doc({'doctype':'Custom Role', 'report':report.name,
        'roles':[{'role':row.role} for row in report.roles] + [{'role':role.name}]}).insert(ignore_permissions=True)
    user = frappe.get_doc({'doctype':'User', 'email':'group.sender@example.invalid',
        'first_name':'Synthetic Sender', 'enabled':1, 'send_welcome_email':0, 'user_type':'System User',
        'roles':[{'role':role.name}, {'role':'ERPNext WhatsApp Sender'}]}).insert(ignore_permissions=True)
    frappe.get_doc({'doctype':'User Permission', 'user':user.name, 'allow':'Company',
        'for_value':company.name, 'apply_to_all_doctypes':1}).insert(ignore_permissions=True)
    from frappe.utils.password import update_password
    password = secrets.token_urlsafe(32)
    update_password(user.name, password)
    editor_role = frappe.get_doc({'doctype':'Role', 'role_name':'Synthetic settings writer',
        'desk_access':1}).insert(ignore_permissions=True)
    for target in ('Company', SETTINGS):
        name = add_permission(target, editor_role.name, ptype='read')
        permission = frappe.get_doc('Custom DocPerm', name)
        permission.write = int(target == SETTINGS)
        permission.save(ignore_permissions=True)
    # In this disposable fixture, the old Manager label carries connection
    # administration only. Group editing must come from the new arbitrary
    # role's actual native Settings Write, not that label.
    for name in frappe.get_all('Custom DocPerm', filters={'parent':SETTINGS,
            'role':'ERPNext WhatsApp Manager'}, pluck='name'):
        permission = frappe.get_doc('Custom DocPerm', name)
        permission.write = 0
        permission.save(ignore_permissions=True)
    frappe.clear_cache(doctype=SETTINGS)
    editor = frappe.get_doc({'doctype':'User', 'email':'group.editor@example.invalid',
        'first_name':'Synthetic Editor', 'enabled':1, 'send_welcome_email':0, 'user_type':'System User',
        'roles':[{'role':editor_role.name}, {'role':'ERPNext WhatsApp Manager'}]}).insert(ignore_permissions=True)
    frappe.get_doc({'doctype':'User Permission', 'user':editor.name, 'allow':'Company',
        'for_value':company.name, 'apply_to_all_doctypes':1}).insert(ignore_permissions=True)
    editor_password = secrets.token_urlsafe(32)
    update_password(editor.name, editor_password)
    frappe.db.commit()
    return company, other, customer, invoice, user.name, password, editor.name, editor_password


def check_delivery(result, peer, *, expected_group=True):
    from erpnext_whatsapp_connection.outbound import TERMINAL_STATUSES
    primary = frappe.get_doc(HISTORY, result['name'])
    assert primary.status == 'Queued'
    if expected_group:
        copy = frappe.get_doc(HISTORY, result['group_copy']['name'])
        assert copy.status == 'Waiting for Primary' and copy.copy_of == primary.name
        assert primary.pdf_sha256 == copy.pdf_sha256
        assert primary.pdf_file != copy.pdf_file and primary.idempotency_key != copy.idempotency_key
        for delivery in (primary, copy):
            file = frappe.get_doc('File', delivery.pdf_file)
            assert file.is_private and file.attached_to_name == delivery.name
    run_worker()
    primary.reload()
    assert primary.status in TERMINAL_STATUSES, 'Native primary worker did not confirm submission'
    if expected_group:
        copy.reload()
        assert copy.status == 'Queued', 'Primary did not release its separate copy job'
        run_worker()
        copy.reload()
        assert copy.status in TERMINAL_STATUSES, 'Native copy worker did not confirm submission'
        assert peer.deliveries[copy.idempotency_key]['recipient_type'] == 'Group'
        assert peer.deliveries[copy.idempotency_key]['recipient'] == GROUP
        assert peer.deliveries[primary.idempotency_key]['pdfs'] == peer.deliveries[copy.idempotency_key]['pdfs']
    else:
        assert 'group_copy' not in result
    return primary


def validate():
    require_fixture_site()
    from erpnext_whatsapp_connection import api
    from erpnext_whatsapp_connection.company_groups import configured_group, list_groups
    from erpnext_whatsapp_connection.outbound import process_outbound_message
    original_user = frappe.session.user
    original_test = frappe.flags.in_test
    frappe.flags.in_test = True
    try:
        frappe.set_user('Administrator')
        stage('native_records_and_permissions')
        company, other, customer, invoice, sender, password, editor, editor_password = setup_documents()
        from erpnext_whatsapp_connection.group_browser_acceptance import native_http, validate_browser
        with tempfile.TemporaryDirectory(prefix='whatsapp-native-capture-') as directory:
            with ProtocolPeer(Path(directory)) as peer, captured_gateway(peer), native_http():
                stage('enabled_configuration_and_repeated_migration')
                settings = frappe.get_single(SETTINGS)
                settings.enabled = 1
                settings.maximum_retries = 1
                settings.require_submitted_documents = 0  # Only a draft synthetic invoice; no GL posting.
                settings.company_groups[0].enabled = 1
                settings.save(ignore_permissions=True)
                assert settings.company_groups[0].group_id == GROUP
                assert any(row['value'] == GROUP for row in list_groups(company.name))
                settings.reload()
                assert settings.company_groups[0].enabled == 1
                assert configured_group(settings, other.name) is None
                snapshot = [(row.name,row.company,row.group_id,row.enabled) for row in settings.company_groups]
                frappe.db.commit()
                for _ in range(2):
                    subprocess.run(['bench','--site','integration.local','migrate'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=True)
                frappe.db.rollback()
                settings.reload()
                assert snapshot == [(row.name,row.company,row.group_id,row.enabled) for row in settings.company_groups]

                def queue_invoice():
                    frappe.set_user(sender)
                    return api.queue_document('Sales Invoice', invoice.name, '+12025550123',
                        'Standard', 'Synthetic document copy', str(invoice.modified))

                frappe.set_user(sender)
                stage('forged_and_cross_company_denials')
                count = frappe.db.count(HISTORY)
                for recipient in (GROUP, OTHER_GROUP):
                    try:
                        api.queue_document('Sales Invoice', invoice.name, recipient,
                            'Standard', 'Synthetic forged recipient', str(invoice.modified))
                    except frappe.ValidationError:
                        frappe.clear_last_message()
                    else:
                        raise AssertionError('A caller-selected group was accepted as a customer number')
                try:
                    api.prepare_report('Accounts Receivable', {'company':other.name,
                        'party':[customer.name], 'party_type':'Customer'})
                except frappe.PermissionError:
                    frappe.clear_last_message()
                else:
                    raise AssertionError('Report preparation accepted a forbidden Company')
                assert frappe.db.count(HISTORY) == count, 'Denied requests created delivery records'

                stage('document_queue_and_native_rq_workers')
                primary = check_delivery(queue_invoice(), peer)
                before = len(peer.deliveries)
                process_outbound_message(primary.name)
                assert len(peer.deliveries) == before, 'Completed primary was resent'
                frappe.set_user(sender)
                stage('report_pdf_queue_and_native_rq_workers')
                report_filters = {'company':company.name,
                    'party':[customer.name], 'party_type':'Customer',
                    'report_date':str(date.today()), 'ageing_based_on':'Due Date', 'range':'30, 60, 90, 120'}
                normalized = api._validate_report('Accounts Receivable', report_filters)[1]
                from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport
                native_report = ReceivablePayableReport(normalized)
                native_report.account_type = 'Receivable'
                native_report.add_common_filters()
                assert str(native_report.ple.party.isin([customer.name])) in [
                    str(condition) for condition in native_report.qb_selection_filter
                ], 'Native report did not bind the validated customer to its query'
                result = api.queue_report('Accounts Receivable', report_filters,
                    '+12025550123', 'Synthetic report copy')
                assert json.loads(frappe.get_doc(HISTORY, result['name']).report_filters)['party'] == [customer.name]
                check_delivery(result, peer)

                # A known failed copy can retry through the real scheduler/RQ
                # path without any second primary provider request.
                stage('copy_only_scheduler_retry')
                result = queue_invoice()
                run_worker()
                primary = frappe.get_doc(HISTORY, result['name'])
                peer.group_failures = 1
                run_worker()
                copy = frappe.get_doc(HISTORY, result['group_copy']['name'])
                assert copy.status == 'Failed' and copy.next_retry_at and not copy.reconciliation_required
                from frappe.utils import add_to_date, now_datetime
                frappe.db.set_value(HISTORY, copy.name, 'next_retry_at', add_to_date(now_datetime(), seconds=-1))
                from erpnext_whatsapp_connection.outbound import retry_due_messages
                retry_due_messages()
                run_worker()
                copy.reload()
                assert copy.status == 'Submitted to WhatsApp'
                assert peer.attempts[primary.idempotency_key] == 1 and peer.attempts[copy.idempotency_key] == 2

                result = queue_invoice()
                run_worker()  # Child is queued but has not run yet.
                stage('sender_revocation_before_copy')
                frappe.set_user('Administrator')
                actor = frappe.get_doc('User', sender)
                actor.set('roles', [{'role':'Synthetic company report reader'}])
                actor.save(ignore_permissions=True)
                frappe.db.commit()
                before = len(peer.deliveries)
                run_worker()
                denied = frappe.get_doc(HISTORY, result['group_copy']['name'])
                assert denied.status == 'Failed' and len(peer.deliveries) == before
                actor.append('roles', {'role':'ERPNext WhatsApp Sender'})
                actor.save(ignore_permissions=True)
                frappe.db.commit()

                result = queue_invoice()
                run_worker()
                stage('source_revocation_before_copy')
                frappe.set_user('Administrator')
                actor.reload()
                actor.set('roles', [{'role':'ERPNext WhatsApp Sender'}])
                actor.save(ignore_permissions=True)
                frappe.db.commit()
                before = dict(peer.attempts)
                run_worker()
                assert frappe.get_doc(HISTORY, result['group_copy']['name']).status == 'Failed'
                assert peer.attempts == before, 'Source Read/Print revocation still reached transport'
                actor.append('roles', {'role':'Synthetic company report reader'})
                actor.save(ignore_permissions=True)
                frappe.db.commit()

                settings.reload()
                stage('disabled_copy_primary_only')
                settings.company_groups[0].enabled = 0
                settings.save(ignore_permissions=True)
                frappe.db.commit()
                check_delivery(queue_invoice(), peer, expected_group=False)

                frappe.set_user('Administrator')
                settings.reload()
                settings.company_groups[0].enabled = 1
                settings.save(ignore_permissions=True)
                frappe.db.commit()
                result = queue_invoice()
                run_worker()
                stage('uncertain_copy_reconciliation_no_replay')
                peer.group_failures = 1
                peer.uncertain = True
                run_worker()
                uncertain = frappe.get_doc(HISTORY, result['group_copy']['name'])
                assert uncertain.status == 'Failed' and uncertain.reconciliation_required and not uncertain.next_retry_at
                before = dict(peer.attempts)
                process_outbound_message(uncertain.name)
                assert peer.attempts == before, 'Uncertain copy was replayed'

                stage('actual_settings_browser_and_native_api_denials')
                validate_browser(company.name, other.name, sender, password, editor, editor_password)
        from erpnext_whatsapp_connection import __version__
        evidence = {'native_enabled_group_acceptance':'PASS', 'site':'integration.local',
            'app_version':__version__, 'document_and_report_workers':True,
            'private_pdf_and_separate_history':True, 'company_disabled_and_revocation':True,
            'copy_only_retry_without_primary_resend':True, 'native_source_revocation_before_transport':True,
            'forged_group_and_cross_company_requests_denied':True,
            'native_receivable_party_filter':True,
            'uncertain_copy_no_replay':True, 'enabled_mapping_repeated_migration':True,
            'actual_settings_browser':True, 'external_messages':False}
        print('WHATSAPP_NATIVE_GROUP_ACCEPTANCE=' + json.dumps(evidence), flush=True)
        return evidence
    finally:
        frappe.set_user(original_user)
        frappe.flags.in_test = original_test
