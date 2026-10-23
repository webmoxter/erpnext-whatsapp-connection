import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from test_company_groups import Row


class GroupIdentityTests(TestCase):
    def setUp(self):
        path=Path(__file__).parents[1]/'erpnext_whatsapp_connection/erpnext_whatsapp_connection/doctype/erpnext_whatsapp_delivery_history/erpnext_whatsapp_delivery_history.py'
        node=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.ClassDef))
        self.before=Row(status='Queued',recipient_type='Group',recipient='********',copy_of='primary',
            reference_type='Document',reference_doctype='Sales Invoice',reference_name='Synthetic Invoice',
            idempotency_key='Synthetic original identity',message_text='Synthetic content')
        self.doc=Row(self.before);self.doc.get_doc_before_save=lambda:self.before
        scope={'Document':object,'frappe':NS(throw=lambda message:(_ for _ in ()).throw(PermissionError(message))),
            '_':lambda text:text}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        self.validate=scope['ERPNextWhatsAppDeliveryHistory'].validate

    def test_copy_payload_destination_and_retry_identity_cannot_be_changed(self):
        for field,value in [('idempotency_key','Replacement key'),('copy_of','Foreign parent'),
                ('owner','another@example.invalid'),('recipient','999999999999@g.us'),
                ('message_text','Forged message'),('pdf_file','Foreign file'),('recipient_type','Individual')]:
            old=self.doc.get(field);self.doc[field]=value
            with self.subTest(field=field),self.assertRaises(PermissionError):self.validate(self.doc)
            self.doc[field]=old

    def test_worker_status_and_attempt_updates_remain_allowed(self):
        self.doc.status='Failed';self.doc.retry_count=1;self.doc.error_message='Synthetic safe error'
        self.validate(self.doc)


class RetryConfigurationTests(TestCase):
    def test_zero_retries_is_not_replaced_with_the_default(self):
        path=Path(__file__).parents[1]/'erpnext_whatsapp_connection/erpnext_whatsapp_connection/doctype/erpnext_whatsapp_settings/erpnext_whatsapp_settings.py'
        node=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.ClassDef))
        scope={'Document':object,'frappe':NS(throw=lambda message:(_ for _ in ()).throw(ValueError(message))),
            '_':lambda text:text,'cint':lambda value:int(value or 0)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
        guard=Mock()
        with patch.dict('sys.modules',{'erpnext_whatsapp_connection.company_groups':NS(validate_settings=guard)}):
            for configured,expected in ((0,0),(None,3),(2,2),(50,5)):
                doc=Row(provider='Linked Device',throttle_seconds=10,maximum_retries=configured)
                scope['ERPNextWhatsAppSettings'].validate(doc)
                self.assertEqual(doc.maximum_retries,expected)
