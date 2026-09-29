import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTBOUND = ROOT / "erpnext_whatsapp_connection" / "outbound.py"


class RetrySafetyContractTest(unittest.TestCase):
    def setUp(self):
        self.source = OUTBOUND.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_retry_limit_clears_due_timestamp(self):
        self.assertIn('document.next_retry_at = None', self.source)
        self.assertIn('Automatic retry limit reached', self.source)
        self.assertIn('attempts >= _attempt_limit(document)', self.source)

    def test_scheduler_claims_due_retry_before_enqueue(self):
        retry_function = next(
            node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "retry_due_messages"
        )
        calls = [
            node
            for node in ast.walk(retry_function)
            if isinstance(node, ast.Call)
        ]
        set_value_lines = [
            node.lineno
            for node in calls
            if isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "frappe"
            and node.func.value.attr == "db"
            and node.func.attr == "set_value"
        ]
        enqueue_lines = [
            node.lineno
            for node in calls
            if isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "frappe"
            and node.func.attr == "enqueue"
        ]
        self.assertTrue(set_value_lines)
        self.assertEqual(len(enqueue_lines), 1)
        self.assertLess(min(set_value_lines), enqueue_lines[0])
        self.assertIn('{"status": "Queued", "next_retry_at": None}', self.source)

    def test_retry_job_identity_is_attempt_scoped(self):
        self.assertIn('job_id=f"whatsapp-retry:{row.name}:{cint(row.retry_count) + 1}"', self.source)

    def test_processing_and_backoff_duplicates_are_rejected(self):
        self.assertIn('document.status == "Processing"', self.source)
        self.assertIn('document.status == "Failed" and document.next_retry_at and document.next_retry_at > now', self.source)


if __name__ == "__main__":
    unittest.main()
