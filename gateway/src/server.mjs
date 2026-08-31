import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import pino from 'pino';
import { safeError, verifyRequest } from './core.mjs';
import { WhatsAppGateway } from './gateway.mjs';
import { GatewayStore } from './store.mjs';

const socketPath = process.env.ERPNEXT_WHATSAPP_SOCKET || '/run/erpnext-whatsapp/gateway.sock';
const authPath = process.env.ERPNEXT_WHATSAPP_AUTH_DB || '/var/lib/erpnext-whatsapp-auth/auth.sqlite';
const statePath = process.env.ERPNEXT_WHATSAPP_STATE_DB || '/var/lib/erpnext-whatsapp-state/state.sqlite';
const masterKeyFile = process.env.ERPNEXT_WHATSAPP_MASTER_KEY_FILE || '/run/secrets/erpnext_whatsapp_auth_master_key';
const hmacKeyFile = process.env.ERPNEXT_WHATSAPP_HMAC_KEY_FILE || '/run/secrets/erpnext_whatsapp_gateway_hmac';

function readSecret(filename, label) {
  const value = fs.readFileSync(filename, 'utf8').trim();
  if (value.length < 32) throw new Error(`${label} must contain at least 32 characters.`);
  return value;
}

const logger = pino({ level: process.env.ERPNEXT_WHATSAPP_LOG_LEVEL || 'info' });
const gateway = new WhatsAppGateway({
  store: new GatewayStore({ authPath, statePath, masterSecret: readSecret(masterKeyFile, 'Authentication master key') }),
  throttleMs: Number(process.env.ERPNEXT_WHATSAPP_THROTTLE_MS || 10_000),
  logger,
});
const hmacSecret = readSecret(hmacKeyFile, 'Gateway HMAC key');
const seenNonces = new Map();

function json(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body), 'Cache-Control': 'no-store' });
  res.end(body);
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 70 * 1024 * 1024) throw new Error('Request body is too large.');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

function authenticate(req, pathname, rawBody) {
  const timestamp = req.headers['x-erpnext-whatsapp-timestamp'];
  const nonce = req.headers['x-erpnext-whatsapp-nonce'];
  const signature = req.headers['x-erpnext-whatsapp-signature'];
  const now = Date.now();
  for (const [key, expires] of seenNonces) if (expires < now) seenNonces.delete(key);
  if (seenNonces.has(nonce)) return false;
  const valid = verifyRequest(hmacSecret, { timestamp, nonce, method: req.method, path: pathname, body: rawBody }, signature, now);
  if (valid) seenNonces.set(nonce, now + 300_000);
  return valid;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    const rawBody = await readBody(req);
    if (url.pathname !== '/health' && !authenticate(req, url.pathname, rawBody)) return json(res, 401, { error: 'Unauthorized gateway request.' });
    const body = rawBody ? JSON.parse(rawBody) : {};
    if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, { ok: true, service: 'erpnext-whatsapp-gateway' });
    if (req.method === 'POST' && url.pathname === '/v1/status') return json(res, 200, gateway.status(body.tenant_id, body.provider));
    if (req.method === 'POST' && url.pathname === '/v1/connect') return json(res, 200, await gateway.connect(body.tenant_id, body.provider));
    if (req.method === 'POST' && url.pathname === '/v1/disconnect') return json(res, 200, await gateway.disconnect(body.tenant_id, body.provider));
    if (req.method === 'POST' && url.pathname === '/v1/cloud/configure') return json(res, 200, await gateway.configureCloud(body.tenant_id, body));
    if (req.method === 'POST' && url.pathname === '/v1/send') return json(res, 200, await gateway.send(body));
    if (req.method === 'POST' && url.pathname === '/v1/events') return json(res, 200, { events: gateway.store.eventsAfter(body.tenant_id, body.after_id) });
    if (req.method === 'POST' && url.pathname === '/v1/cloud/webhook/verify') {
      return json(res, 200, { challenge: gateway.verifyCloudWebhook(body.tenant_id, body.verify_token, body.challenge) });
    }
    if (req.method === 'POST' && url.pathname === '/v1/cloud/webhook') {
      const webhookBody = Buffer.from(String(body.payload_base64 || ''), 'base64').toString('utf8');
      return json(res, 200, gateway.receiveCloudWebhook(body.tenant_id, webhookBody, body.signature));
    }
    return json(res, 404, { error: 'Not found.' });
  } catch (error) {
    return json(res, 400, { error: safeError(error) });
  }
});

const expectedRoot = '/run/erpnext-whatsapp';
if (path.dirname(socketPath) !== expectedRoot) throw new Error('Gateway socket must remain in the protected runtime directory.');
fs.mkdirSync(expectedRoot, { recursive: true, mode: 0o770 });
try { fs.unlinkSync(socketPath); } catch (error) { if (error.code !== 'ENOENT') throw error; }
server.listen(socketPath, () => {
  fs.chmodSync(socketPath, 0o660);
  logger.info({ event: 'gateway_started', transport: 'unix_socket' }, 'ERPNext WhatsApp gateway started');
  gateway.initialize().catch(() => undefined);
});

function shutdown() {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 5_000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
