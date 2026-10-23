"""Fixture safety, actual signed Unix HTTP and fail-closed evidence parsing.

Native Frappe/RQ/Chromium acceptance itself runs exclusively in integration CI.
"""
import ast
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeGroupFixtureTests(unittest.TestCase):
    def module(self, site='integration.local', enabled=1):
        fr = NS(local=NS(site=site), conf={'whatsapp_integration_acceptance':enabled})
        with patch.dict(sys.modules, {'frappe':fr}):
            module = load('native_group_fixture_test', 'erpnext_whatsapp_connection/group_acceptance.py')
            browser = load('native_group_browser_test', 'erpnext_whatsapp_connection/group_browser_acceptance.py')
        return module, browser

    def test_fixture_refuses_production_and_non_opted_in_sites_before_runtime_access(self):
        for site, enabled in (('production.invalid',1), ('integration.local',0), ('other.local',1)):
            module, _ = self.module(site, enabled)
            for function, args in ((module.validate, ()), (module.setup_documents, ()),
                                   (module.worker_once, ('expected-job',)), (module.run_worker, ('expected-message',))):
                with self.subTest(site=site,function=function.__name__), self.assertRaises(RuntimeError):
                    function(*args)

    def test_native_worker_executes_bootstrap_jobs_and_stops_before_copy(self):
        module, _ = self.module()
        target = NS(kwargs={'site':'integration.local',
            'method':'erpnext_whatsapp_connection.outbound.process_outbound_message'}, status='queued')
        target.get_status = lambda **_:target.status
        bootstrap = NS(kwargs={'site':'integration.local', 'method':'frappe.search.website_search.build_index_for_all_routes'})
        child = NS(kwargs=dict(target.kwargs))
        bootstrap.status = 'queued'
        bootstrap.get_status = lambda **_:bootstrap.status
        pending = [bootstrap, target, child]
        executed = []
        queue = NS(connection=object(), count=3,
            get_jobs=lambda **_:pending[:1])
        def work(**kwargs):
            self.assertEqual(kwargs['max_jobs'], 1)
            job = pending.pop(0)
            executed.append(job)
            job.status = 'finished'
        worker = Mock(return_value=NS(work=work))
        native = NS(get_job=Mock(return_value=target), get_queue=Mock(return_value=queue))
        with patch.dict(sys.modules, {'frappe.utils.background_jobs':native, 'rq':NS(Worker=worker)}):
            module.worker_once('expected-job')
        self.assertEqual(executed, [bootstrap, target])
        self.assertEqual(pending, [child])
        native.get_job.assert_called_once_with('expected-job')

        # A native bootstrap failure must not be silently passed over merely
        # because the expected delivery itself could succeed afterwards.
        pending[:] = [bootstrap, target, child]
        bootstrap.status = target.status = 'queued'
        def failed_work(**_):
            pending.pop(0).status = 'failed'
        worker.return_value.work = failed_work
        with patch.dict(sys.modules, {'frappe.utils.background_jobs':native, 'rq':NS(Worker=worker)}):
            with self.assertRaisesRegex(AssertionError, 'Native queued job failed'):
                module.worker_once('expected-job')
        self.assertEqual(pending, [target, child])

    def test_native_worker_refuses_missing_foreign_completed_or_unbounded_work(self):
        module, _ = self.module()
        for site, method, status, count, foreign_head in (
                ('foreign.invalid','erpnext_whatsapp_connection.outbound.process_outbound_message','queued',1,False),
                ('integration.local','other.method','queued',1,False),
                ('integration.local','erpnext_whatsapp_connection.outbound.process_outbound_message','finished',1,False),
                ('integration.local','erpnext_whatsapp_connection.outbound.process_outbound_message','queued',51,False),
                ('integration.local','erpnext_whatsapp_connection.outbound.process_outbound_message','queued',1,True)):
            with self.subTest(site=site,method=method,status=status,count=count,foreign_head=foreign_head):
                target = NS(kwargs={'site':site,'method':method}, get_status=lambda **_:status)
                head = NS(kwargs={'site':'foreign.invalid' if foreign_head else 'integration.local'})
                queue = NS(connection=object(), count=count, get_jobs=lambda **_:[head])
                worker = Mock()
                native = NS(get_job=Mock(return_value=target), get_queue=Mock(return_value=queue))
                with patch.dict(sys.modules, {'frappe.utils.background_jobs':native, 'rq':NS(Worker=worker)}):
                    with self.assertRaises(AssertionError):
                        module.worker_once('expected-job')
                worker.assert_not_called()
        native.get_job.return_value = None
        with patch.dict(sys.modules, {'frappe.utils.background_jobs':native, 'rq':NS(Worker=worker)}):
            with self.assertRaises(AssertionError):
                module.worker_once('missing-job')

    def test_actual_unix_protocol_validates_signature_tenant_and_replay(self):
        module, _ = self.module()
        with patch.dict(sys.modules, {'frappe':NS(local=NS(site='integration.local'))}):
            client = load('native_group_gateway_client_test', 'erpnext_whatsapp_connection/gateway_client.py')
        with tempfile.TemporaryDirectory() as directory, module.ProtocolPeer(Path(directory)) as peer:
            self.assertEqual(peer.key_file.stat().st_mode & 0o777, 0o600)
            client.SOCKET_PATH = str(peer.socket)
            client.HMAC_KEY_FILE = str(peer.key_file)
            result = client.gateway_request('/v1/groups', {'tenant_id':'integration.local'})
            self.assertEqual(result['groups'][0]['id'], module.GROUP)
            with self.assertRaises(client.WhatsAppGatewayError):
                client.gateway_request('/v1/groups', {'tenant_id':'foreign.invalid'})
            body = json.dumps({'tenant_id':'integration.local'}).encode()
            stamp, nonce = str(int(time.time())), 'synthetic-replay-nonce'
            canonical = f'{stamp}\n{nonce}\nPOST\n/v1/groups\n{hashlib.sha256(body).hexdigest()}'.encode()
            headers = {'Content-Length':str(len(body)), 'X-ERPNext-WhatsApp-Timestamp':stamp,
                'X-ERPNext-WhatsApp-Nonce':nonce,
                'X-ERPNext-WhatsApp-Signature':hmac.new(peer.key,canonical,hashlib.sha256).hexdigest()}
            statuses = []
            for _ in range(2):
                connection = client._UnixHTTPConnection(str(peer.socket))
                connection.request('POST','/v1/groups',body,headers)
                response = connection.getresponse()
                statuses.append(response.status)
                response.read()
                connection.close()
            self.assertEqual(statuses, [200,403])

    def test_fixture_tree_links_are_leaves_under_the_existing_or_new_root(self):
        for doctype, field, parent_field in (
                ('Customer Group','customer_group_name','parent_customer_group'),
                ('Territory','territory_name','parent_territory'),
                ('Item Group','item_group_name','parent_item_group')):
            for existing_root in ('Existing native root', None):
                with self.subTest(doctype=doctype, root=existing_root):
                    module, _ = self.module()
                    inserted = []
                    def document(values):
                        values = dict(values)
                        name = values[field]
                        def insert(*, ignore_permissions):
                            self.assertTrue(ignore_permissions)
                            inserted.append(values)
                            return NS(name=name)
                        return NS(insert=insert)
                    module.frappe.get_doc = document
                    root_lookup = Mock(return_value=existing_root)
                    with patch.dict(sys.modules, {'frappe.utils.nestedset':NS(get_root_of=root_lookup)}):
                        result = module.fixture_tree_leaf(doctype, field, parent_field, 'Synthetic leaf')
                    root_lookup.assert_called_once_with(doctype)
                    self.assertEqual(result, 'Synthetic leaf')
                    self.assertEqual(inserted[-1], {'doctype':doctype, field:'Synthetic leaf',
                        parent_field:existing_root or 'Synthetic leaf Root', 'is_group':0})
                    self.assertEqual(len(inserted), 1 if existing_root else 2)
                    if not existing_root:
                        self.assertEqual(inserted[0], {'doctype':doctype,
                            field:'Synthetic leaf Root', 'is_group':1})

    def test_fixture_tree_creation_refuses_non_fixture_sites_before_tree_lookup(self):
        module, _ = self.module('production.invalid')
        module.frappe.get_doc = Mock()
        with self.assertRaises(RuntimeError):
            module.fixture_tree_leaf('Customer Group','customer_group_name',
                'parent_customer_group','Synthetic leaf')
        module.frappe.get_doc.assert_not_called()

    def test_ci_requires_enabled_native_stage_and_checked_evidence(self):
        compose = (ROOT/'compose.integration.yaml').read_text()
        workflow = (ROOT/'.github/workflows/ci.yml').read_text()
        self.assertIn('execute erpnext_whatsapp_connection.group_acceptance.validate', compose)
        self.assertIn('whatsapp_integration_acceptance 1', compose)
        self.assertIn('Require native enabled-group evidence', workflow)
        self.assertIn('scripts/verify-native-group-evidence.py', workflow)
        self.assertNotIn('continue-on-error', workflow)

    def test_composer_asset_cache_identity_uses_current_application_version(self):
        hooks = load('native_group_hooks_test', 'erpnext_whatsapp_connection/hooks.py')
        from erpnext_whatsapp_connection import __version__
        self.assertTrue(hooks.app_include_js.endswith('?v=' + __version__))

    def test_browser_diagnostics_exclude_payloads_hosts_query_strings_and_record_paths(self):
        _, browser = self.module()
        secret = 'sensitive-fixture-value'
        details = {'text':secret, 'url':'http://private.invalid/assets/frappe/dist/js/desk.js?token='+secret,
            'lineNumber':12, 'columnNumber':4,
            'exception':{'className':'TypeError', 'description':secret, 'value':{'recipient':secret}},
            'stackTrace':{'callFrames':[
                {'url':'http://private.invalid/desk/customer/'+secret, 'lineNumber':3, 'columnNumber':1},
                {'url':'http://private.invalid/assets/erpnext/js/utils.js?key='+secret,
                 'lineNumber':8, 'columnNumber':2}]}}
        result = browser.exception_location(details)
        text = json.dumps(result)
        self.assertNotIn(secret, text)
        self.assertNotIn('private.invalid', text)
        self.assertEqual(result['kind'], 'TypeError')
        self.assertEqual(result['source'], '/assets/frappe/dist/js/desk.js')
        self.assertEqual(result['frames'][0]['source'], '[redacted]')
        self.assertEqual(browser.diagnostic_path('https://private.invalid/api/method/frappe.desk.form.load.getdoc?name='+secret),
            '/api/method/frappe.desk.form.load.getdoc')
        self.assertEqual(browser.diagnostic_path('https://private.invalid/api/resource/Customer/'+secret), '[redacted]')

    def test_browser_save_input_dispatches_press_release_and_refuses_unavailable_controls(self):
        _, module = self.module()
        browser = module.Browser()
        browser.evaluate = Mock(return_value={'x':42, 'y':24})
        browser.command = Mock()
        browser.click('cur_frm.page.btn_primary[0]')
        calls = browser.command.call_args_list
        self.assertEqual([call.args[0] for call in calls], ['Input.dispatchMouseEvent'] * 2)
        self.assertEqual([call.args[1]['type'] for call in calls], ['mousePressed','mouseReleased'])
        self.assertEqual([call.args[1]['buttons'] for call in calls], [1,0])
        self.assertTrue(all(call.args[1]['x']==42 and call.args[1]['y']==24 for call in calls))
        for reason in ('missing','disabled','hidden'):
            browser.command.reset_mock()
            browser.evaluate.return_value = {'unavailable':reason}
            with self.assertRaisesRegex(AssertionError, reason):
                browser.click('cur_frm.page.btn_primary[0]')
            browser.command.assert_not_called()


class NativeGroupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.parser = load('native_group_evidence_test', 'scripts/verify-native-group-evidence.py')
        self.result = {'native_enabled_group_acceptance':'PASS', 'site':'integration.local',
            'app_version':'0.1.5', 'external_messages':False,
            **{key:True for key in ('document_and_report_workers', 'private_pdf_and_separate_history',
                'company_disabled_and_revocation', 'uncertain_copy_no_replay',
                'enabled_mapping_repeated_migration', 'actual_settings_browser',
                'copy_only_retry_without_primary_resend', 'native_source_revocation_before_transport',
                'forged_group_and_cross_company_requests_denied', 'native_receivable_party_filter')}}

    def record(self, value=None):
        return 'acceptance-1 | WHATSAPP_NATIVE_GROUP_ACCEPTANCE=' + json.dumps(value or self.result)

    def test_complete_matching_record_is_required(self):
        self.assertEqual(self.parser.verify(self.record(), '0.1.5'), self.result)
        for text in ('', self.record()+'\n'+self.record(), 'WHATSAPP_NATIVE_GROUP_ACCEPTANCE={'):
            with self.subTest(text=text), self.assertRaises((ValueError, json.JSONDecodeError)):
                self.parser.verify(text, '0.1.5')

    def test_every_proof_is_strict_and_missing_false_or_old_evidence_fails(self):
        for key in self.result:
            for value in (None, 'true', 1):
                changed = {**self.result, key:value}
                with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                    self.parser.verify(self.record(changed), '0.1.5')
        with self.assertRaises(ValueError):
            self.parser.verify(self.record(), '0.1.6')


class ReportCompanyAdmissionTests(unittest.TestCase):
    def setUp(self):
        path = ROOT/'erpnext_whatsapp_connection/api.py'
        tree = ast.parse(path.read_text())
        node = next(node for node in tree.body if isinstance(node,ast.FunctionDef)
                    and node.name == '_validate_report')
        node.decorator_list = []
        self.report = NS(ref_doctype='Sales Invoice', is_permitted=Mock(return_value=True))
        self.company = NS(check_permission=Mock())
        self.customer = NS(check_permission=Mock())
        self.fr = NS(parse_json=json.loads, PermissionError=PermissionError,
            has_permission=Mock(return_value=True),
            throw=lambda message,*_:(_ for _ in ()).throw(PermissionError(message)),
            get_doc=Mock(side_effect=lambda dt,name: self.report if dt=='Report'
                        else self.company if dt=='Company' else self.customer))
        scope = self.scope = {'frappe':self.fr,'_':lambda text:text,'report_adapter':lambda _: {
            'customer_filter':'customer','company_filter':'company'}}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        self.validate = scope['_validate_report']

    def test_native_report_and_customer_and_company_are_independently_required(self):
        result = self.validate('Accounts Receivable', {'customer':['Synthetic'], 'company':'Permitted'})
        self.assertEqual(result[-1],'Permitted')
        self.customer.check_permission.assert_called_once_with('read')
        self.company.check_permission.assert_called_once_with('read')
        self.report.is_permitted.return_value = False
        with self.assertRaises(PermissionError):
            self.validate('Accounts Receivable', {'customer':'Synthetic','company':'Permitted'})

    def test_empty_forged_or_forbidden_company_does_not_acquire_report_scope(self):
        for company in ('', None, ['Forged'], {'name':'Forged'}):
            with self.subTest(company=company), self.assertRaises(PermissionError):
                self.validate('Accounts Receivable', {'customer':'Synthetic','company':company})
        self.company.check_permission.side_effect = PermissionError('Other company')
        with self.assertRaisesRegex(PermissionError,'Other company'):
            self.validate('Accounts Receivable', {'customer':'Synthetic','company':'Forbidden'})

    def test_registered_company_independent_reports_keep_their_individual_send_contract(self):
        self.scope['report_adapter'] = lambda _: {'customer_filter':'customer'}
        self.assertEqual(self.validate('Registered customer report', {'customer':'Synthetic'})[-1], '')
        self.company.check_permission.assert_not_called()

    def test_built_in_report_filters_match_native_party_field_and_shape(self):
        with patch.dict(sys.modules, {'frappe':NS()}):
            adapters = load('native_report_adapters_test', 'erpnext_whatsapp_connection/adapters.py')
        self.scope['report_adapter'] = adapters.DEFAULT_REPORT_ADAPTERS.get
        for report, adapter in adapters.DEFAULT_REPORT_ADAPTERS.items():
            for selection in ('Synthetic', ['Synthetic']):
                with self.subTest(report=report, selection=selection):
                    filters = {'party':selection, 'party_type':'Customer', 'company':'Permitted'}
                    actual = self.validate(report, filters)[1]
                    expected = 'Synthetic' if report == 'Customer Ledger Summary' else ['Synthetic']
                    self.assertEqual(actual['party'], expected)
                    self.assertEqual(filters['party'], selection, 'Caller filters were mutated')
            for selection in (None, [], ['Synthetic', 'Other'], {'name':'Synthetic'}):
                with self.subTest(report=report, forged=selection), self.assertRaises(PermissionError):
                    self.validate(report, {'party':selection, 'customer':'Synthetic',
                        'party_type':'Customer', 'company':'Permitted'})
            if adapter.get('party_type_filter'):
                for party_type in (None, '', 'Supplier'):
                    with self.subTest(report=report, party_type=party_type), self.assertRaises(PermissionError):
                        self.validate(report, {'party':['Synthetic'], 'party_type':party_type,
                            'company':'Permitted'})

    def test_invalid_registered_filter_shape_fails_closed(self):
        self.scope['report_adapter'] = lambda _: {'customer_filter':'party', 'customer_filter_type':'unknown'}
        with self.assertRaises(PermissionError):
            self.validate('Registered customer report', {'party':'Synthetic'})


if __name__ == '__main__':
    unittest.main()
