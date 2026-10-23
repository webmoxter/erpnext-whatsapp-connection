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
            for function in (module.validate, module.setup_documents, module.worker_once, module.run_worker):
                with self.subTest(site=site,function=function.__name__), self.assertRaises(RuntimeError):
                    function()

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


class NativeGroupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.parser = load('native_group_evidence_test', 'scripts/verify-native-group-evidence.py')
        self.result = {'native_enabled_group_acceptance':'PASS', 'site':'integration.local',
            'app_version':'0.1.5', 'external_messages':False,
            **{key:True for key in ('document_and_report_workers', 'private_pdf_and_separate_history',
                'company_disabled_and_revocation', 'uncertain_copy_no_replay',
                'enabled_mapping_repeated_migration', 'actual_settings_browser',
                'copy_only_retry_without_primary_resend', 'native_source_revocation_before_transport',
                'forged_group_and_cross_company_requests_denied')}}

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


if __name__ == '__main__':
    unittest.main()
