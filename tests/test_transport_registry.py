import importlib
import sys
import unittest
from types import ModuleType
from unittest.mock import patch


class FakeFrappe(ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.hooks = []
        self.attributes = {}

    def get_hooks(self, _name):
        return self.hooks

    def get_attr(self, path):
        return self.attributes[path]

    def throw(self, message):
        raise RuntimeError(message)


def load_transports():
    fake = FakeFrappe()
    with patch.dict(sys.modules, {"frappe": fake}):
        sys.modules.pop("erpnext_whatsapp_connection.transports", None)
        sys.modules.pop("erpnext_whatsapp_connection.gateway_client", None)
        module = importlib.import_module("erpnext_whatsapp_connection.transports")
    return module, fake


class TransportRegistryTest(unittest.TestCase):
    def test_builtin_transports_are_registered(self):
        module, _fake = load_transports()
        registry = module.transport_registry()
        self.assertEqual(registry["Linked Device"]["gateway_provider"], "Baileys")
        self.assertEqual(registry["Official API"]["gateway_provider"], "Official API")

    def test_external_app_can_replace_official_transport(self):
        module, fake = load_transports()
        fake.hooks = ["example.transport_registry"]
        fake.attributes["example.transport_registry"] = lambda: {
            "Official API": {"send": "example.send"}
        }
        registry = module.transport_registry()
        self.assertEqual(registry["Official API"], {"send": "example.send"})
        self.assertIn("Linked Device", registry)

    def test_invalid_transport_fails_closed(self):
        module, _fake = load_transports()
        with self.assertRaisesRegex(RuntimeError, "not registered"):
            module.get_transport("Unknown")


if __name__ == "__main__":
    unittest.main()
