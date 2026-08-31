import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTest(unittest.TestCase):
    def test_all_json_files_parse(self):
        for filename in ROOT.rglob("*.json"):
            if "node_modules" in filename.parts or ".git" in filename.parts:
                continue
            json.loads(filename.read_text(encoding="utf-8"))

    def test_public_source_contains_no_private_deployment_identifiers(self):
        forbidden = (
            "tfo" + ".erpfin360.com",
            "gac" + ".erpfin360.com",
            "premcorp" + ".erpfin360.com",
            ".".join(("13", "60", "148", "194")),
            "037547" + "369922",
            "+923343" + "441765",
        )
        for filename in ROOT.rglob("*"):
            if (
                not filename.is_file()
                or ".git" in filename.parts
                or "node_modules" in filename.parts
            ):
                continue
            if filename.suffix.lower() not in {
                ".py", ".js", ".mjs", ".json", ".md", ".toml", ".yml"
            }:
                continue
            content = filename.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, content, f"private identifier found in {filename}: {value}")

    def test_security_boundaries_are_present(self):
        api = (ROOT / "erpnext_whatsapp_connection" / "api.py").read_text(encoding="utf-8")
        outbound = (ROOT / "erpnext_whatsapp_connection" / "outbound.py").read_text(encoding="utf-8")
        self.assertIn('doc.check_permission("read")', api)
        self.assertIn('ptype="print"', api)
        self.assertIn("recipient not in allowed_numbers", api)
        self.assertIn("_validate_print_format", api)
        self.assertIn("is_private=1", api)
        self.assertIn("hashlib.sha256(content).hexdigest()", outbound)

    def test_transport_is_replaceable_without_replacing_document_workflow(self):
        hooks = (ROOT / "erpnext_whatsapp_connection" / "hooks.py").read_text(encoding="utf-8")
        transports = (ROOT / "erpnext_whatsapp_connection" / "transports.py").read_text(encoding="utf-8")
        self.assertIn("erpnext_whatsapp_transport_adapter_providers", transports)
        self.assertIn("send_delivery", transports)
        self.assertIn('app_title = "ERPNext WhatsApp Connection by ERPFin360.com"', hooks)

    def test_delivery_history_masks_recipient_and_stores_encrypted_value(self):
        filename = (
            ROOT
            / "erpnext_whatsapp_connection"
            / "erpnext_whatsapp_connection"
            / "doctype"
            / "erpnext_whatsapp_delivery_history"
            / "erpnext_whatsapp_delivery_history.json"
        )
        fields = {
            row["fieldname"]: row
            for row in json.loads(filename.read_text(encoding="utf-8"))["fields"]
        }
        self.assertEqual(fields["recipient"]["fieldtype"], "Password")
        self.assertEqual(fields["recipient"]["hidden"], 1)
        self.assertEqual(fields["recipient_masked"]["read_only"], 1)
        self.assertEqual(fields["pdf_sha256"]["read_only"], 1)


if __name__ == "__main__":
    unittest.main()
