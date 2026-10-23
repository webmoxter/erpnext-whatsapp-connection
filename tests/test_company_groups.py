import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch


class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class CompanyGroupsTests(TestCase):
    def setUp(self):
        self.group='120000000000000000@g.us'
        self.company=NS(check_permission=Mock())
        self.primary=Row(doctype='ERPNext WhatsApp Delivery History',name='primary',owner='actor@example.invalid',
            company='Synthetic Company', provider='Linked Device',status='Submitted to WhatsApp',
            reference_type='Document',reference_doctype='Sales Invoice',reference_name='Synthetic Invoice',
            source_modified='2026-01-01 00:00:00',pdf_sha256='Synthetic digest',message_text='Synthetic text')
        self.copy=Row(self.primary,name='copy',copy_of='primary',recipient_type='Group',status='Queued')
        self.copy.get_password=Mock(return_value=self.group)
        self.rule=Row(company=self.primary.company,enabled=1,group_id=self.group)
        self.settings=Row(provider='Linked Device',company_groups=[self.rule])
        self.settings.get_doc_before_save=lambda:None
        self.report=NS(is_permitted=Mock(return_value=True))
        def throw(message,*args):raise PermissionError(message)
        self.fr=NS(session=NS(user='worker@example.invalid'),PermissionError=PermissionError,_=lambda text:text,
            throw=throw,whitelist=lambda *a,**k:lambda f:f,has_permission=Mock(return_value=True),
            get_single=Mock(return_value=self.settings),
            get_doc=Mock(side_effect=lambda kind,name:self.company if kind=='Company'
                else self.report if kind=='Report' else self.primary),
            db=NS(get_value=Mock(return_value=1),set_value=Mock()),get_all=Mock(return_value=[]),enqueue=Mock())
        self.fr.set_user=lambda value:setattr(self.fr.session,'user',value)
        self.gateway=Mock(return_value={'groups':[dict(id=self.group,name='Synthetic group')]})
        self.sender=Mock(side_effect=lambda:self.assertEqual(self.fr.session.user,self.primary.owner))
        self.validate_document=Mock(return_value=(Row(company=self.primary.company,modified=self.primary.source_modified),
            {'company_field':'company'}))
        self.validate_print=Mock()
        self.validate_report=Mock(return_value=({}, {}, 'Synthetic Customer',self.primary.company))
        modules={'frappe':self.fr,'frappe.utils':NS(cint=lambda value:int(value or 0)),
            'erpnext_whatsapp_connection.gateway_client':NS(gateway_request=self.gateway,site_payload=lambda **v:dict(tenant_id='integration.local',**v)),
            'erpnext_whatsapp_connection.api':NS(_validate_document=self.validate_document,
                _validate_print_format=self.validate_print,_validate_report=self.validate_report),
            'erpnext_whatsapp_connection.permissions':NS(require_sender=self.sender)}
        context=patch.dict(sys.modules,modules);context.start();self.addCleanup(context.stop)
        spec=importlib.util.spec_from_file_location('company_groups_tested',Path(__file__).parents[1]/'erpnext_whatsapp_connection/company_groups.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def test_company_specific_configuration_has_no_fallback_group(self):
        self.assertEqual(self.module.configured_group(self.settings,self.primary.company),self.group)
        self.assertIsNone(self.module.configured_group(self.settings,'Other company'))
        self.rule.enabled=0
        self.assertIsNone(self.module.configured_group(self.settings,self.primary.company))

    def test_duplicate_company_and_official_transport_are_rejected(self):
        self.settings.company_groups.append(Row(self.rule))
        with self.assertRaises(PermissionError):self.module.validate_settings(self.settings)
        self.settings.company_groups.pop();self.settings.provider='Official API'
        with self.assertRaises(PermissionError):self.module.validate_settings(self.settings)
        self.gateway.assert_not_called()

    def test_configuration_requires_current_joined_group_and_company_access(self):
        self.module.validate_settings(self.settings)
        self.assertEqual(self.rule.group_name,'Synthetic group')
        self.company.check_permission.assert_called_with('read')
        self.gateway.return_value={'groups':[]}
        with self.assertRaises(PermissionError):self.module.validate_settings(self.settings)
        self.company.check_permission.side_effect=PermissionError('Denied company')
        with self.assertRaisesRegex(PermissionError,'Denied company'):
            self.module.validate_settings(self.settings)

    def test_disabling_a_rule_never_contacts_the_gateway(self):
        self.rule.enabled=0
        self.module.validate_settings(self.settings)
        self.gateway.assert_not_called()

    def test_removing_another_company_rule_requires_that_company_permission(self):
        before=Row(company_groups=[Row(self.rule)])
        self.settings.company_groups=[];self.settings.get_doc_before_save=lambda:before
        self.company.check_permission.side_effect=PermissionError('Denied company')
        with self.assertRaisesRegex(PermissionError,'Denied company'):
            self.module.validate_settings(self.settings)

    def test_discovery_requires_native_settings_write_and_company_access(self):
        self.fr.has_permission.return_value=False
        with self.assertRaises(PermissionError):self.module.list_groups(self.primary.company)
        self.gateway.assert_not_called()
        self.fr.has_permission.return_value=True
        self.assertEqual(self.module.list_groups(self.primary.company),[{'value':self.group,'label':'Synthetic group'}])

    def test_copy_checks_original_actor_and_restores_worker_context(self):
        self.assertTrue(self.module.validate_copy(self.copy,self.settings))
        self.sender.assert_called_once_with()
        self.validate_document.assert_called_once_with('Sales Invoice','Synthetic Invoice')
        self.validate_print.assert_called_once_with('Sales Invoice','Standard')
        self.assertEqual(self.fr.session.user,'worker@example.invalid')

    def test_copy_denies_changed_company_group_source_version_or_actor(self):
        for field,value in [('company','Foreign company'),('owner','foreign@example.invalid'),
                ('pdf_sha256','Changed digest'),('reference_name','Other invoice')]:
            old=self.copy[field];self.copy[field]=value
            with self.subTest(field=field),self.assertRaises(PermissionError):
                self.module.validate_copy(self.copy,self.settings)
            self.copy[field]=old
        self.rule.group_id='999999999999@g.us'
        with self.assertRaises(PermissionError):self.module.validate_copy(self.copy,self.settings)
        self.assertEqual(self.fr.session.user,'worker@example.invalid')

    def test_copy_waits_for_primary_and_never_copies_a_copy(self):
        self.primary.status='Failed'
        self.assertFalse(self.module.validate_copy(self.copy,self.settings))
        self.sender.assert_not_called()
        self.primary.status='Submitted to WhatsApp';self.primary.recipient_type='Group'
        with self.assertRaises(PermissionError):self.module.validate_copy(self.copy,self.settings)

    def test_actor_revocation_prevents_validation_and_restores_context(self):
        self.sender.side_effect=PermissionError('Sender revoked')
        with self.assertRaisesRegex(PermissionError,'Sender revoked'):
            self.module.validate_copy(self.copy,self.settings)
        self.validate_document.assert_not_called()
        self.assertEqual(self.fr.session.user,'worker@example.invalid')

    def test_report_copy_requires_original_company_and_current_report_scope(self):
        for row in (self.primary,self.copy):
            row.reference_type='Report';row.report_name='Synthetic report';row.report_filters='{}'
        self.assertTrue(self.module.validate_copy(self.copy,self.settings))
        self.validate_report.assert_called_once_with('Synthetic report','{}')
        self.validate_report.return_value=({}, {}, 'Synthetic Customer','Foreign company')
        with self.assertRaises(PermissionError):self.module.validate_copy(self.copy,self.settings)
        self.report.is_permitted.return_value=False
        with self.assertRaisesRegex(PermissionError,'no longer has access'):
            self.module.validate_copy(self.copy,self.settings)

    def test_released_child_job_is_independent_and_after_commit(self):
        self.fr.get_all.return_value=['copy']
        self.module.release_waiting_copies('primary')
        self.fr.enqueue.assert_called_once()
        call=self.fr.enqueue.call_args.kwargs
        self.assertEqual(call['message_name'],'copy')
        self.assertTrue(call['enqueue_after_commit']);self.assertTrue(call['deduplicate'])
