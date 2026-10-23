"""Disposable fixture setup keeps native Company prerequisites and validation."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


class Row(dict):
    __getattr__ = dict.__getitem__


class AcceptanceSetupTests(unittest.TestCase):
    def setUp(self):
        self.warehouse_types = set()
        self.rows = []
        self.inserted = []
        self.defaults = {}
        self.company_failure = None
        self.settings = Mock()
        self.settings.get.side_effect = lambda key: self.rows if key == 'company_groups' else None
        self.settings.append.side_effect = self.append
        self.presets = Mock(return_value=[{'doctype':'Warehouse Type', 'name':'Transit'},
            {'doctype':'Item Group', 'item_group_name':'Unrelated native fixture'}])
        self.fr = NS(local=NS(site='integration.local'),
            db=NS(exists=Mock(side_effect=lambda kind,name: name in self.warehouse_types
                              if kind == 'Warehouse Type' else False),
                  set_default=Mock(side_effect=self.defaults.__setitem__),
                  get_default=Mock(side_effect=self.defaults.get), commit=Mock(), rollback=Mock()),
            get_single=Mock(return_value=self.settings), get_doc=Mock(side_effect=self.get_doc))
        modules = {'frappe':self.fr,
            'erpnext_whatsapp_connection.install':NS(after_migrate=Mock()),
            'erpnext.setup.setup_wizard.operations.install_fixtures':NS(get_preset_records=self.presets)}
        context = patch.dict('sys.modules', modules)
        context.start()
        self.addCleanup(context.stop)
        spec = importlib.util.spec_from_file_location('whatsapp_acceptance_setup_test',
            Path(__file__).parents[1]/'erpnext_whatsapp_connection/acceptance.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def get_doc(self, values):
        def insert(**kwargs):
            if values['doctype'] == 'Company':
                if 'Transit' not in self.warehouse_types:
                    raise RuntimeError('Could not find Warehouse Type: Transit')
                if self.company_failure:
                    raise self.company_failure
            self.inserted.append(dict(values))
            if values['doctype'] == 'Warehouse Type':
                self.warehouse_types.add(values['name'])
            return NS(name=values.get('name') or values['company_name'])
        return NS(insert=Mock(side_effect=insert))

    def append(self, key, values):
        self.assertEqual(key, 'company_groups')
        row = Row(name='original-synthetic-row', **values)
        self.rows.append(row)
        return row

    def test_fresh_company_uses_native_prerequisites_before_insertion_and_keeps_disabled_snapshot(self):
        # This is the original failure when the prerequisite has not been set up.
        with self.assertRaisesRegex(RuntimeError, 'Could not find Warehouse Type: Transit'):
            self.get_doc({'doctype':'Company', 'company_name':'Synthetic'}).insert()
        result = self.module.prepare_group_preservation()
        self.assertFalse(result['external_messages'])
        self.assertEqual([row['doctype'] for row in self.inserted], ['Warehouse Type', 'Company'])
        self.presets.assert_called_once_with('United States')
        self.assertEqual(self.rows[0].enabled, 0)
        snapshot = json.loads(self.defaults['whatsapp_group_preservation_fixture'])
        self.assertEqual(snapshot['name'], self.rows[0].name)
        self.module.validate_group_preservation()
        self.module.validate_group_preservation()
        self.fr.db.commit.assert_called_once_with()
        self.fr.db.rollback.assert_not_called()

    def test_existing_native_warehouse_type_is_reused_without_mutation(self):
        self.warehouse_types.add('Transit')
        self.module._prepare_company_prerequisites('United States')
        self.module._prepare_company_prerequisites('United States')
        self.fr.get_doc.assert_not_called()
        self.fr.db.commit.assert_not_called()

    def test_production_and_existing_configuration_refused_before_any_writes(self):
        self.fr.local.site = 'production.invalid'
        with self.assertRaises(RuntimeError):
            self.module.prepare_group_preservation()
        with self.assertRaises(RuntimeError):
            self.module._prepare_company_prerequisites('United States')
        self.fr.local.site = 'integration.local'
        self.rows.append(Row(company='Original company', enabled=0))
        with self.assertRaisesRegex(RuntimeError, 'must not overwrite'):
            self.module.prepare_group_preservation()
        self.presets.assert_not_called()
        self.fr.get_doc.assert_not_called()
        self.fr.db.set_default.assert_not_called()
        self.fr.db.commit.assert_not_called()

    def test_missing_or_malformed_native_prerequisites_fail_and_roll_back(self):
        for records in ([], [{'doctype':'Warehouse Type'}],
                        [{'doctype':'Warehouse Type', 'name':17}]):
            with self.subTest(records=records):
                self.presets.return_value = records
                with self.assertRaisesRegex(RuntimeError, 'presets are missing or invalid'):
                    self.module.prepare_group_preservation()
        self.assertEqual(self.fr.db.rollback.call_count, 3)
        self.fr.get_doc.assert_not_called()
        self.fr.db.commit.assert_not_called()

    def test_native_company_error_is_not_bypassed_or_committed(self):
        self.company_failure = RuntimeError('Native Company validation failed')
        with self.assertRaisesRegex(RuntimeError, 'Native Company validation failed'):
            self.module.prepare_group_preservation()
        self.fr.db.rollback.assert_called_once_with()
        self.settings.append.assert_not_called()
        self.fr.db.set_default.assert_not_called()
        self.fr.db.commit.assert_not_called()

    def test_preservation_check_fails_on_missing_snapshot_or_changed_mapping(self):
        with self.assertRaisesRegex(AssertionError, 'fixture is missing'):
            self.module.validate_group_preservation()
        self.module.prepare_group_preservation()
        self.rows[0]['enabled'] = 1
        with self.assertRaisesRegex(AssertionError, 'changed original'):
            self.module.validate_group_preservation()


if __name__ == '__main__':
    unittest.main()
