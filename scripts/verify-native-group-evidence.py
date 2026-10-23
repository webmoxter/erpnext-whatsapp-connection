"""Fail closed if the native installation lane did not execute group acceptance."""
import json
from pathlib import Path
import sys


def verify(text, expected_version):
    marker = 'WHATSAPP_NATIVE_GROUP_ACCEPTANCE='
    rows = [json.loads(line.split(marker, 1)[1]) for line in text.splitlines() if marker in line]
    if len(rows) != 1:
        raise ValueError('Exactly one enabled-group acceptance record is required')
    result = rows[0]
    required = ('document_and_report_workers', 'private_pdf_and_separate_history',
        'company_disabled_and_revocation', 'uncertain_copy_no_replay',
        'enabled_mapping_repeated_migration', 'actual_settings_browser',
        'copy_only_retry_without_primary_resend', 'native_source_revocation_before_transport',
        'forged_group_and_cross_company_requests_denied', 'native_receivable_party_filter')
    if (result.get('native_enabled_group_acceptance') != 'PASS'
            or result.get('site') != 'integration.local'
            or result.get('app_version') != expected_version
            or result.get('external_messages') is not False
            or any(result.get(key) is not True for key in required)):
        raise ValueError('Enabled-group acceptance evidence is missing, false or mismatched')
    return result


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from erpnext_whatsapp_connection import __version__
    verify(sys.stdin.read(), __version__)
    print('NATIVE_GROUP_EVIDENCE=PASS')
