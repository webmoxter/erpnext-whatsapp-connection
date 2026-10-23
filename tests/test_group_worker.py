import ast
from datetime import datetime, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from test_company_groups import Row


class GroupWorkerTests(TestCase):
    def setUp(self):
        import json
        self.now=datetime(2026,1,1)
        self.doc=Row(name='copy',recipient_type='Group',copy_of='primary',status='Queued',
            retry_count=0,max_retries=3,message_text='Synthetic copy')
        self.doc.save=Mock()
        self.fr=NS(get_doc=Mock(return_value=self.doc),db=NS(get_value=Mock(return_value='Submitted to WhatsApp')),
            get_single=Mock(return_value=Row(enabled=1)),utils=NS(get_system_timezone=lambda:'UTC'),
            throw=lambda message:(_ for _ in ()).throw(RuntimeError(message)))
        self.send=Mock(return_value={'message_ids':['group-message'],'submitted_at':self.now})
        self.guard=Mock(return_value=True);self.release=Mock()
        self.pdf=Mock(return_value=[{'filename':'invoice.pdf','content_base64':'synthetic'}])
        path=Path(__file__).parents[1]/'erpnext_whatsapp_connection/outbound.py'
        tree=ast.parse(path.read_text())
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef)
            and node.name in {'_attempt_limit','process_outbound_message'}]
        self.scope=dict(frappe=self.fr,_=lambda text:text,json=json,cint=lambda v:int(v or 0),
            now_datetime=lambda:self.now,add_to_date=lambda value,seconds:value+timedelta(seconds=seconds),
            HISTORY_DOCTYPE='ERPNext WhatsApp Delivery History',RETRY_DELAYS_SECONDS=(30,120,600),
            TERMINAL_STATUSES={'Submitted to WhatsApp','Acknowledged by WhatsApp'},
            _pdf_payload=self.pdf,send_delivery=self.send,provider_datetime=lambda value,zone:value)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),self.scope)
        ctx=patch.dict(sys.modules,{'erpnext_whatsapp_connection.company_groups':NS(
            validate_copy=self.guard,release_waiting_copies=self.release)})
        ctx.start();self.addCleanup(ctx.stop)

    def run_worker(self):
        self.scope['process_outbound_message']('copy')

    def test_copy_waits_without_attempting_when_primary_has_not_succeeded(self):
        self.fr.db.get_value.return_value='Failed';self.doc.status='Waiting for Primary'
        self.run_worker()
        self.send.assert_not_called();self.doc.save.assert_not_called()
        self.assertEqual(self.doc.retry_count,0)

    def test_successful_copy_never_releases_or_reexecutes_primary(self):
        self.run_worker()
        self.guard.assert_called_once_with(self.doc,self.fr.get_single.return_value)
        self.pdf.assert_called_once_with(self.doc);self.send.assert_called_once()
        self.assertEqual(self.doc.status,'Submitted to WhatsApp')
        self.release.assert_not_called()
        self.run_worker();self.send.assert_called_once()

    def test_uncertain_copy_outcome_stops_automatic_replay(self):
        error=RuntimeError('Uncertain group submission');error.reconciliation_required=True
        self.send.side_effect=error
        self.run_worker()
        self.assertEqual(self.doc.status,'Failed')
        self.assertEqual(self.doc.reconciliation_required,1)
        self.assertIsNone(self.doc.next_retry_at)
        self.assertIn('requires reconciliation',self.doc.result_message)
        self.run_worker();self.send.assert_called_once()
        self.release.assert_not_called()

    def test_revoked_source_denies_before_private_pdf_or_transport(self):
        self.guard.side_effect=PermissionError('Current source denied')
        self.run_worker()
        self.pdf.assert_not_called();self.send.assert_not_called()
        self.assertEqual(self.doc.status,'Failed')

    def test_completed_primary_releases_only_children_without_resending_primary(self):
        self.doc.copy_of=None;self.doc.recipient_type='Individual'
        self.doc.status='Submitted to WhatsApp'
        self.run_worker()
        self.release.assert_called_once_with('copy')
        self.send.assert_not_called()
