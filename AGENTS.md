# Repository instructions

This repository is a generic Frappe/ERPNext WhatsApp add-on. Keep it independent
from ERPFin360 and from every tenant, company, deployment host, phone number,
credential, logo, and private DocType.

Enforce document and report permissions on the server. Never trust a hidden
button, caller-selected DocType, report, attachment, print format, recipient, or
message template without validation. Do not log message contents, recipient
numbers, credentials, QR payloads, PDF bytes, or authentication state.

Public releases require a clean secret-history scan, dependency-license review,
tests, tagged immutable artifacts, and security documentation.
