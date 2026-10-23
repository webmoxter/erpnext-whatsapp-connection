import frappe

from erpnext_whatsapp_connection.install import after_migrate


REQUIRED_DOCTYPES = (
    "ERPNext WhatsApp Settings",
    "ERPNext WhatsApp Message Template",
    "ERPNext WhatsApp Delivery History",
    "ERPNext WhatsApp Company Group",
)
REQUIRED_ROLES = ("ERPNext WhatsApp Manager", "ERPNext WhatsApp Sender")


def validate_installation():
    """Fail closed when a real installed site is missing the public contract."""
    after_migrate()
    after_migrate()
    for doctype in REQUIRED_DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            frappe.throw(f"Missing installed DocType: {doctype}")
    for role in REQUIRED_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.throw(f"Missing installed role: {role}")
    if not frappe.db.exists(
        "ERPNext WhatsApp Message Template", "Default Sales Invoice"
    ):
        frappe.throw("Default Sales Invoice message template was not seeded")
    if frappe.db.count(
        "ERPNext WhatsApp Message Template", {"name": "Default Sales Invoice"}
    ) != 1:
        frappe.throw("Default Sales Invoice message template is not idempotent")
    frappe.get_single("ERPNext WhatsApp Settings")
    validate_group_preservation()
    return {
        "app": "erpnext_whatsapp_connection",
        "doctypes": list(REQUIRED_DOCTYPES),
        "roles": list(REQUIRED_ROLES),
        "repeat_migration": "passed",
        "company_group_settings_preserved": True,
    }


def prepare_group_preservation():
    """Synthetic, disabled configuration must survive both real migrations."""
    if frappe.local.site != 'integration.local':
        raise RuntimeError('Group preservation requires the disposable integration site')
    import json
    settings = frappe.get_single('ERPNext WhatsApp Settings')
    if settings.get('company_groups'):
        raise RuntimeError('Fresh group fixture must not overwrite existing configuration')
    country = 'United States'
    try:
        _prepare_company_prerequisites(country)
        company = frappe.get_doc({'doctype':'Company', 'company_name':'WhatsApp Fixture Company',
            'abbr':'WAF', 'default_currency':'USD', 'country':country}).insert(ignore_permissions=True)
        row = settings.append('company_groups', {'company':company.name, 'enabled':0,
            'group_id':'120000000000000000@g.us', 'group_name':'Synthetic disabled group'})
        settings.save(ignore_permissions=True)
        frappe.db.set_default('whatsapp_group_preservation_fixture', json.dumps({
            'company':company.name, 'name':row.name, 'group_id':row.group_id, 'enabled':0}))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise
    return {'disabled_synthetic_group_fixture':'READY', 'external_messages':False}


def _prepare_company_prerequisites(country):
    """Use installed native presets, without running the global Setup Wizard.

    A fresh bench install has not run the wizard. Native Company insertion
    creates warehouses that reference the wizard's Warehouse Type records.
    Keep those native validations enabled and prepare only that prerequisite.
    """
    if frappe.local.site != 'integration.local':
        raise RuntimeError('Company prerequisites require the disposable integration site')
    from erpnext.setup.setup_wizard.operations.install_fixtures import get_preset_records

    records = [dict(row) for row in get_preset_records(country)
               if row.get('doctype') == 'Warehouse Type']
    if not records or any(not isinstance(row.get('name'), str) or not row['name']
                          for row in records):
        raise RuntimeError('Native company Warehouse Type presets are missing or invalid')
    for record in records:
        if not frappe.db.exists('Warehouse Type', record['name']):
            frappe.get_doc(record).insert(ignore_permissions=True)


def validate_group_preservation():
    if frappe.local.site != 'integration.local':
        raise RuntimeError('Group preservation requires the disposable integration site')
    import json
    snapshot = json.loads(frappe.db.get_default('whatsapp_group_preservation_fixture') or '{}')
    if not snapshot:
        raise AssertionError('Original group preservation fixture is missing')
    rows = frappe.get_single('ERPNext WhatsApp Settings').get('company_groups') or []
    if len(rows) != 1 or any(rows[0].get(key) != value for key,value in snapshot.items()):
        raise AssertionError('Migration changed original company group configuration')
