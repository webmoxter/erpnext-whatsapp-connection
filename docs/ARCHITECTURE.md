# Architecture

The add-on separates the user workflow from the message transport.

1. A document or report adapter declares the permitted customer, company, amount,
   date, and default message context.
2. The server verifies read, print, report, source-state, recipient, print-format,
   and sender-role permissions.
3. A private PDF snapshot and checksum are attached to an immutable delivery record.
4. A background worker loads the selected transport through the provider registry.
5. The transport submits the message and returns provider identifiers and status.
6. Scheduled reconciliation updates delivery history without exposing credentials.

Custom applications may register document, report, and transport providers through:

- `erpnext_whatsapp_document_adapter_providers`
- `erpnext_whatsapp_report_adapter_providers`
- `erpnext_whatsapp_transport_adapter_providers`

Product-specific DocTypes and reports belong in each consuming application's
private adapter and must never be copied into this repository.
