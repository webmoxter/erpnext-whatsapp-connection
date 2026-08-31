# Security policy

Please report security vulnerabilities privately to `support@tngsol.com`.
Do not open a public issue containing credentials, phone numbers, message bodies,
QR payloads, authentication state, private PDFs, tenant names, or deployment details.

## Security boundaries

- Every document and report action is permission-checked on the server.
- Recipient numbers must resolve from the permitted customer, contact, or address.
- PDF snapshots are private and their SHA-256 digest is checked before delivery.
- Gateway requests use signed, replay-resistant messages over a Unix-domain socket.
- Provider credentials and linked-device authentication remain outside the Frappe database.
- The gateway must not expose a public TCP listener.

The project does not support unsolicited bulk messaging, recipient scraping,
rate-limit evasion, or bypassing WhatsApp or Meta policies.
