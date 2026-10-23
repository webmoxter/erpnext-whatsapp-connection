import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { validateGroupId } from '../src/core.mjs';
import { WhatsAppGateway } from '../src/gateway.mjs';
import { GatewayStore } from '../src/store.mjs';

function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-group-'));
  const store = new GatewayStore({ authPath: path.join(directory, 'auth.sqlite'),
    statePath: path.join(directory, 'state.sqlite'), masterSecret: 'x'.repeat(64) });
  t.after(() => { store.close(); fs.rmSync(directory, { recursive: true, force: true }); });
  const gateway = new WhatsAppGateway({ store });
  // Exercise the actual send/SQLite path without waiting the provider throttle.
  // SequentialQueue and real throttle behavior retain their separate tests.
  gateway.queue.add = work => work();
  const tenant = 'group.integration.test';
  const id = '120000000000000000@g.us';
  const own = '12025550187@s.whatsapp.net';
  const calls = [];
  const socket = {
    user: { id: own },
    groupFetchAllParticipating: async () => ({ [id]: { id, subject: 'Synthetic business group' } }),
    groupMetadata: async value => ({ id: value, participants: [{ id: own }], announce: false }),
    sendMessage: async (target, part) => { calls.push({ target, part }); return { key: { id: 'part-' + calls.length } }; },
  };
  gateway.sessions.set(tenant, { socket });
  gateway.setStatus(tenant, 'Connected', { provider: 'Baileys', connected: true });
  const request = { tenant_id: tenant, provider: 'Baileys', recipient_type: 'Group', recipient: id,
    text: 'Synthetic invoice copy', pdfs: [{ filename: 'invoice.pdf', content_base64: Buffer.from('%PDF-1.7\nfixture').toString('base64') }],
    idempotency_key: 'wa:group:synthetic-copy-1' };
  return { gateway, store, socket, request, tenant, id, calls };
}

test('group identifiers cannot be confused with individual numbers, URLs or broadcasts', () => {
  assert.equal(validateGroupId('120000000000000000@g.us'), '120000000000000000@g.us');
  assert.equal(validateGroupId('12345678-1234567890@g.us'), '12345678-1234567890@g.us');
  for (const value of ['+12025550187', '12345@s.whatsapp.net', 'status@broadcast', 'https://example.test', ' 1234567890@g.us', {}, null]) {
    assert.throws(() => validateGroupId(value));
  }
});

test('joined group discovery is tenant-local and exposes no participant records', async t => {
  const { gateway, tenant, id } = fixture(t);
  assert.deepEqual(await gateway.groups(tenant), [{ id, name: 'Synthetic business group' }]);
  await assert.rejects(gateway.groups('other.integration.test'), /not connected/);
});

test('group CC has independent durable identity and completed replay sends nothing', async t => {
  const { gateway, store, request, calls } = fixture(t);
  const result = await gateway.send(request);
  assert.equal(result.success, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].target, request.recipient);
  assert.equal(result.recipient_masked, 'Configured company group');
  assert.equal((await gateway.send(request)).replayed, true);
  assert.equal(calls.length, 2);
  await assert.rejects(gateway.send({ ...request, text: 'Different payload' }), /payload changed/);
  assert.equal(store.getJob(request.idempotency_key).tenant_id, request.tenant_id);
});

test('unjoined group, wrong provider and announcement posting restrictions send nothing', async t => {
  const { gateway, socket, request, calls } = fixture(t);
  await assert.rejects(gateway.send({ ...request, provider: 'Official API' }), /Linked Device/);
  await assert.rejects(gateway.send({ ...request, recipient: '999999999999@g.us',
    idempotency_key: request.idempotency_key + '-unjoined' }), /no longer joined/);
  socket.groupMetadata = async () => ({ id: request.recipient, participants: [{ id: socket.user.id }], announce: true });
  await assert.rejects(gateway.send(request), /cannot post/);
  assert.equal(calls.length, 0);
});

test('partial group send checkpoints confirmed parts and forbids uncertain replay', async t => {
  const { gateway, store, socket, request, calls } = fixture(t);
  const native = socket.sendMessage;
  socket.sendMessage = async (id, part) => {
    if (part.text) throw Error('Synthetic lost acknowledgement');
    return native(id, part);
  };
  await assert.rejects(gateway.send(request), error => error.reconciliation_required === true);
  const saved = JSON.parse(store.getJob(request.idempotency_key).result_json);
  assert.equal(saved.reconciliation_required, true);
  assert.equal(saved.inflight, true);
  assert.deepEqual(saved.message_ids, ['part-1']);
  await assert.rejects(gateway.send(request), error => error.reconciliation_required === true);
  assert.equal(calls.length, 1);
});

test('a durable in-flight marker survives a process interruption', async t => {
  const { gateway, store, socket, request, calls } = fixture(t);
  socket.sendMessage = async () => { throw Error('Synthetic process interruption'); };
  await assert.rejects(gateway.send(request));
  // Even if the failure handler did not run, the pre-send marker blocks replay.
  const row = store.getJob(request.idempotency_key);
  const progress = JSON.parse(row.result_json);
  delete progress.reconciliation_required;
  store.updateJob({ idempotencyKey: request.idempotency_key, tenant: request.tenant_id,
    status: 'Processing', result: progress });
  await assert.rejects(gateway.send(request), error => error.reconciliation_required === true);
  assert.equal(calls.length, 0);
});

test('a different tenant cannot reuse a successful or failed idempotency key', async t => {
  const { gateway, request } = fixture(t);
  await gateway.send(request);
  await assert.rejects(gateway.send({ ...request, tenant_id: 'foreign.integration.test' }), /another tenant/);
});
