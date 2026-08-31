import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTest(unittest.TestCase):
    def test_stable_release_contract_is_present(self):
        version = (ROOT / "erpnext_whatsapp_connection" / "__init__.py").read_text()
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn('__version__ = "0.1.0"', version)
        self.assertIn("isImmutable", workflow)
        self.assertIn("verify-release-tag.sh", workflow)
        self.assertIn("release-manifest.json", workflow)
        self.assertIn("containerimage.digest", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("--draft=false", workflow)
        self.assertIn("bash scripts/verify-release-tag.sh", workflow)
        self.assertIn("corepack prepare pnpm@11.19.0 --activate", workflow)
        self.assertIn("pnpm install --frozen-lockfile --ignore-scripts", workflow)
        self.assertIn("Require exact-commit CI provenance", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("SOURCE_COMMIT", workflow)
        self.assertIn("python scripts/scan-public-history.py", workflow)

    def test_release_manifest_is_deterministic_and_digest_pinned(self):
        script = ROOT / "scripts" / "build-release-manifest.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            asset = root / "package.whl"
            asset.write_bytes(b"audited-package")
            subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "v0.1.0",
                    "a" * 40,
                    "ghcr.io/webmoxter/gateway@sha256:" + "b" * 64,
                    str(asset),
                ],
                cwd=root,
                check=True,
            )
            manifest = json.loads((root / "release-manifest.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["release"], "0.1.0")
        self.assertEqual(manifest["source_commit"], "a" * 40)
        self.assertRegex(manifest["assets"]["package.whl"]["sha256"], r"^[0-9a-f]{64}$")

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

    def test_real_frappe_installation_contract_is_mandatory(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        compose = (ROOT / "compose.integration.yaml").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile.integration").read_text(encoding="utf-8")
        self.assertIn("Real Frappe ERPNext installation", workflow)
        self.assertIn("--exit-code-from acceptance", workflow)
        self.assertIn("install-app erpnext_whatsapp_connection", compose)
        self.assertEqual(compose.count("bench --site integration.local migrate"), 2)
        self.assertIn("validate_installation", compose)
        self.assertIn("frappe/erpnext:v16.32.3@sha256:", dockerfile)

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
