"""Offline policy tests for opt-in document automation.

Integration CI separately installs the new DocTypes in real Frappe.  These
unit tests use no WhatsApp transport, database, secrets, or external recipients.
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
AUTOMATION = ROOT / "erpnext_whatsapp_connection" / "automation.py"
SETTINGS = ROOT / "erpnext_whatsapp_connection" / "erpnext_whatsapp_connection" / "doctype" / "erpnext_whatsapp_settings" / "erpnext_whatsapp_settings.json"
RULE = ROOT / "erpnext_whatsapp_connection" / "erpnext_whatsapp_connection" / "doctype" / "erpnext_whatsapp_automation_rule" / "erpnext_whatsapp_automation_rule.json"
REQUEST = ROOT / "erpnext_whatsapp_connection" / "erpnext_whatsapp_connection" / "doctype" / "erpnext_whatsapp_automation_request" / "erpnext_whatsapp_automation_request.json"


def load_module():
    fake_frappe = types.ModuleType("frappe")
    fake_frappe.__path__ = []
    fake_frappe.session = SimpleNamespace(user="submitter@example.com")
    fake_frappe.local = SimpleNamespace(site="integration.local")
    fake_frappe.PermissionError = type("FakePermissionError", (Exception,), {})
    fake_frappe.ValidationError = type("FakeValidationError", (Exception,), {})
    fake_frappe.DoesNotExistError = type("FakeDoesNotExistError", (Exception,), {})
    fake_frappe._ = lambda message: message
    fake_frappe.whitelist = lambda **kwargs: lambda fn: fn
    fake_frappe.db = SimpleNamespace(
        exists=lambda *args: False,
        get_value=lambda *args: 1,
    )
    fake_frappe.set_user = lambda user: setattr(fake_frappe.session, "user", user)
    fake_frappe.enqueue = mock.Mock()
    fake_frappe.log_error = mock.Mock()

    exceptions = types.ModuleType("frappe.exceptions")
    exceptions.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
    utils = types.ModuleType("frappe.utils")
    utils.cint = lambda value: int(value or 0)
    utils.now_datetime = lambda: "2026-11-09 12:00:00"

    pkg = types.ModuleType("erpnext_whatsapp_connection")
    pkg.__path__ = [str(ROOT / "erpnext_whatsapp_connection")]
    api = types.ModuleType("erpnext_whatsapp_connection.api")
    api.TEMPLATE_DOCTYPE = "ERPNext WhatsApp Message Template"
    api._store_delivery = mock.Mock(return_value={"name": "WA-TEST-0001"})
    permissions = types.ModuleType("erpnext_whatsapp_connection.permissions")
    permissions.is_manager = lambda user=None: True

    modules = {
        "frappe": fake_frappe,
        "frappe.exceptions": exceptions,
        "frappe.utils": utils,
        "erpnext_whatsapp_connection": pkg,
        "erpnext_whatsapp_connection.api": api,
        "erpnext_whatsapp_connection.permissions": permissions,
    }
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location(
            "erpnext_whatsapp_connection.automation", AUTOMATION
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, fake_frappe, api


def rule(mode="Approval Required"):
    return SimpleNamespace(
        name="AUTO-RULE-1",
        company="Test Company",
        document_type="Sales Invoice",
        enabled=1,
        delivery_mode=mode,
        message_template="",
        print_format="",
    )


def settings(enabled=1, mode="Approval Required"):
    values = {
        "automation_enabled": 1,
        "automation_rules": [rule(mode)],
    }
    return SimpleNamespace(
        enabled=enabled,
        get=lambda name: values.get(name),
    )


def payload():
    return {
        "recipient": "+15551234567",
        "customer": "Test Customer",
        "phone_digest": "digest",
        "modified": "2026-11-09 12:00:00",
        "message": "A synthetic document notification",
        "print_format": "Standard",
        "template_name": "",
    }


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.auto, self.frappe, self.api = load_module()
        self.created = []
        self.frappe.get_single = lambda name: settings()
        self.frappe.get_doc = self.get_doc

    def get_doc(self, value, name=None):
        if isinstance(value, dict):
            record = SimpleNamespace(**value)
            record.insert = lambda ignore_permissions=False: self.created.append(record)
            return record
        raise AssertionError("Unexpected external lookup")

    def document(self):
        return SimpleNamespace(
            doctype="Sales Invoice",
            docstatus=1,
            name="SINV-SYNTHETIC-0001",
            company="Test Company",
        )

    def test_automation_disabled_by_default_in_schema(self):
        settings_json = json.loads(SETTINGS.read_text())
        fields = {field["fieldname"]: field for field in settings_json["fields"]}
        self.assertEqual(fields["automation_enabled"]["default"], "0")
        self.assertEqual(fields["automation_rules"]["options"], "ERPNext WhatsApp Automation Rule")
        rule_json = json.loads(RULE.read_text())
        rule_fields = {field["fieldname"]: field for field in rule_json["fields"]}
        self.assertEqual(rule_fields["enabled"]["default"], "0")
        self.assertEqual(rule_fields["delivery_mode"]["default"], "Approval Required")
        request_json = json.loads(REQUEST.read_text())
        self.assertFalse(any(p.get("write") or p.get("create") for p in request_json["permissions"]))

    def test_company_scoped_rules_and_duplicate_denial(self):
        self.assertIsNone(self.auto._rule(settings(enabled=0), "Test Company", "Sales Invoice"))
        self.assertIsNone(self.auto._rule(settings(), "Other Company", "Sales Invoice"))
        self.assertIsNotNone(self.auto._rule(settings(), "Test Company", "Sales Invoice"))
        both = settings()
        values = {"automation_enabled": 1, "automation_rules": [rule(), rule()]}
        both.get = lambda key: values.get(key)
        with self.assertRaises(self.auto.AutomationPolicyError):
            self.auto._rule(both, "Test Company", "Sales Invoice")

    def test_deterministic_site_bound_request_key(self):
        key = self.auto._request_key("Sales Invoice", "SINV-SYNTHETIC-0001")
        self.assertEqual(key, self.auto._request_key("Sales Invoice", "SINV-SYNTHETIC-0001"))
        self.frappe.local.site = "other.local"
        self.assertNotEqual(key, self.auto._request_key("Sales Invoice", "SINV-SYNTHETIC-0001"))

    def test_submission_prepares_approval_without_queueing(self):
        with mock.patch.object(self.auto, "_prepare_payload", return_value=payload()):
            self.auto.on_document_submit(self.document())
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0].status, "Pending Approval")
        self.assertEqual(self.created[0].message_preview, payload()["message"])
        self.frappe.enqueue.assert_not_called()

    def test_optional_auto_dispatch_uses_after_commit(self):
        self.frappe.get_single = lambda name: settings(mode="Send Automatically")
        with mock.patch.object(self.auto, "_prepare_payload", return_value=payload()):
            self.auto.on_document_submit(self.document())
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.created[0].status, "Approved")
        self.frappe.enqueue.assert_called_once()
        self.assertTrue(self.frappe.enqueue.call_args.kwargs["enqueue_after_commit"])
        self.assertEqual(self.frappe.enqueue.call_args.kwargs["queue"], "long")

    def test_missing_consent_never_queues_or_blocks_document(self):
        with mock.patch.object(
            self.auto, "_prepare_payload",
            side_effect=self.auto.AutomationPolicyError("consent_missing"),
        ):
            self.assertIsNone(self.auto.on_document_submit(self.document()))
        self.assertEqual(self.created, [])
        self.frappe.enqueue.assert_not_called()

    def test_approval_requires_review_and_schedules_after_commit(self):
        request = SimpleNamespace(
            name="WA-AUTO-SYNTHETIC", status="Pending Approval",
            delivery_mode="Approval Required",
            requested_by="submitter@example.com",
            save=mock.Mock(),
        )
        self.frappe.session.user = "manager@example.com"
        with mock.patch.object(self.auto, "_locked_request", return_value=request), \
             mock.patch.object(self.auto, "_validate_request", return_value=payload()):
            result = self.auto.approve_request(request.name)
        self.assertEqual(result["status"], "Approved")
        self.assertEqual(request.approved_by, "manager@example.com")
        self.assertEqual(request.save.call_count, 1)
        self.assertEqual(self.frappe.enqueue.call_count, 1)

    def test_rejection_cannot_queue(self):
        request = SimpleNamespace(
            name="WA-AUTO-SYNTHETIC", status="Pending Approval",
            save=mock.Mock(),
        )
        with mock.patch.object(self.auto, "_locked_request", return_value=request):
            self.auto.reject_request(request.name)
        self.assertEqual(request.status, "Rejected")
        self.frappe.enqueue.assert_not_called()

    def test_dispatch_reuses_private_pdf_queue_without_group_expansion(self):
        request = SimpleNamespace(
            name="WA-AUTO-SYNTHETIC", status="Approved", delivery_history=None,
            delivery_mode="Approval Required",
            approved_by="manager@example.com", requested_by="submitter@example.com",
            reference_doctype="Sales Invoice", reference_name="SINV-SYNTHETIC-0001",
            company="Test Company", save=mock.Mock(),
        )
        prepared = dict(payload(), pdf=b"%PDF-synthetic",
            document=SimpleNamespace(modified="2026-11-09 12:00:00"))
        with mock.patch.object(self.auto, "_locked_request", return_value=request), \
             mock.patch.object(self.auto, "_validate_request", return_value=prepared):
            self.auto.dispatch_approved(request.name)
        self.assertEqual(request.status, "Queued")
        self.assertEqual(request.delivery_history, "WA-TEST-0001")
        self.api._store_delivery.assert_called_once()
        self.assertFalse(self.api._store_delivery.call_args.kwargs["include_group_copy"])
        self.auto.dispatch_approved = self.auto.dispatch_approved
        with mock.patch.object(self.auto, "_locked_request", return_value=request):
            self.auto.dispatch_approved(request.name)
        self.assertEqual(self.api._store_delivery.call_count, 1)


if __name__ == "__main__":
    unittest.main()
