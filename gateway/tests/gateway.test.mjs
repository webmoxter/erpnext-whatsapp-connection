import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import {
  SequentialQueue,
  buildDocumentPayload,
  buildTextPayload,
  normalizeInternationalNumber,
  safeError,
  signRequest,
  verifyRequest,
} from '../src/core.mjs';
import { WhatsAppGateway } from '../src/gateway.mjs';
import { GatewayStore } from '../src/store.mjs';

test('normalizes valid international numbers and rejects malformed values', () => {
  assert.equal(normalizeInternationalNumber('+1 202-555-0187'), '12025550187');
  assert.equal(normalizeInternationalNumber('0012025550187'), '12025550187');
  assert.throws(() => normalizeInternationalNumber('0202 5550187'), /country code/i);
  assert.throws(() => normalizeInternationalNumber('123'), /valid international/i);
});

test('constructs official text and PDF payloads without credentials', () => {
  assert.deepEqual(buildTextPayload('12025550187', 'Test'), {
    messaging_product: 'whatsapp', recipient_type: 'individual', to: '12025550187',
    type: 'text', text: { preview_url: false, body: 'Test' },
  });
  assert.equal(buildDocumentPayload('12025550187', 'media-1', 'invoice.pdf').document.filename, 'invoice.pdf');
});

test('redacts token-like values and validates signed local requests', () => {
  assert.match(safeError(new Error('token=abcdefghijklmnopqrstuvwxyz123456')), /\[REDACTED\]/);
  const request = { timestamp: Math.floor(Date.now() / 1000), nonce: '0123456789abcdef', method: 'POST', path: '/v1/status', body: '{}' };
  const signature = signRequest('a'.repeat(64), request);
  assert.equal(verifyRequest('a'.repeat(64), request, signature), true);
  assert.equal(verifyRequest('b'.repeat(64), request, signature), false);
});

test('sequential queue never runs two jobs concurrently', async () => {
  const queue = new SequentialQueue(0);
  let active = 0;
  let maximum = 0;
  await Promise.all([1, 2, 3].map(() => queue.add(async () => {
    active += 1;
    maximum = Math.max(maximum, active);
    await new Promise((resolve) => setTimeout(resolve, 10));
    active -= 1;
  })));
  assert.equal(maximum, 1);
});

test('gateway status is safe and idempotency prevents duplicate submissions', async (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'erpnext-wa-'));
  const store = new GatewayStore({
    authPath: path.join(directory, 'auth.sqlite'), statePath: path.join(directory, 'state.sqlite'), masterSecret: 'm'.repeat(64),
  });
  const gateway = new WhatsAppGateway({ store, throttleMs: 0 });
  const status = gateway.status('site.example.test');
  assert.equal(status.status, 'Disconnected');
  assert.equal('credentials' in status, false);
  assert.equal('access_token' in status, false);
  gateway.setStatus('site.example.test', 'Connected', { provider: 'Baileys', connected: true });
  assert.equal(gateway.status('site.example.test', 'Baileys').status, 'Connected');
  assert.equal(gateway.status('site.example.test', 'Official API').status, 'Disconnected');
  let calls = 0;
  gateway.sendCloud = async () => { calls += 1; return ['provider-message-1']; };
  const request = {
    tenant_id: 'site.example.test', provider: 'Official API', recipient: '+12025550187', text: 'Test message',
    pdfs: [], idempotency_key: 'test:site:1234567890',
  };
  const first = await gateway.send(request);
  const replay = await gateway.send(request);
  assert.equal(first.success, true);
  assert.equal(replay.replayed, true);
  assert.equal(calls, 1);
  store.close();
  fs.rmSync(directory, { recursive: true, force: true });
});

test('official send fails safely while disconnected and unconfigured', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'erpnext-wa-disconnected-'));
  const store = new GatewayStore({
    authPath: path.join(directory, 'auth.sqlite'), statePath: path.join(directory, 'state.sqlite'), masterSecret: 'm'.repeat(64),
  });
  const gateway = new WhatsAppGateway({ store, throttleMs: 0 });
  await assert.rejects(() => gateway.send({
    tenant_id: 'site.example.test', provider: 'Official API', recipient: '+12025550187', text: 'Test message',
    pdfs: [], idempotency_key: 'test:site:disconnected:123456',
  }), /not configured/i);
  const job = store.getJob('test:site:disconnected:123456');
  assert.equal(job.status, 'Failed');
  assert.equal(job.result_json.includes('access_token'), false);
  store.close();
  fs.rmSync(directory, { recursive: true, force: true });
});
