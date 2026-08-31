import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { BufferJSON, initAuthCreds, proto } from 'baileys';
import { encryptedCodec, safeTenantId } from './core.mjs';

function ensureParent(filename) {
  fs.mkdirSync(path.dirname(filename), { recursive: true, mode: 0o700 });
}

export class GatewayStore {
  constructor({ authPath, statePath, masterSecret }) {
    ensureParent(authPath);
    ensureParent(statePath);
    this.codec = encryptedCodec(masterSecret);
    this.auth = new DatabaseSync(authPath);
    this.state = new DatabaseSync(statePath);
    this.auth.exec(`
      PRAGMA journal_mode=WAL;
      PRAGMA synchronous=FULL;
      CREATE TABLE IF NOT EXISTS secrets (
        tenant_id TEXT NOT NULL, bucket TEXT NOT NULL, item_key TEXT NOT NULL,
        encrypted_value TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, bucket, item_key)
      );
    `);
    this.state.exec(`
      PRAGMA journal_mode=WAL;
      CREATE TABLE IF NOT EXISTS jobs (
        idempotency_key TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, status TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0, result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS provider_messages (
        message_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, idempotency_key TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
        idempotency_key TEXT NOT NULL, status TEXT NOT NULL,
        message TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
      );
    `);
  }

  setSecret(tenantValue, bucket, key, value) {
    const tenant = safeTenantId(tenantValue);
    const now = new Date().toISOString();
    this.auth.prepare(`INSERT INTO secrets VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, bucket, item_key) DO UPDATE SET encrypted_value=excluded.encrypted_value, updated_at=excluded.updated_at`)
      .run(tenant, bucket, key, this.codec.encrypt(value), now);
  }

  getSecret(tenantValue, bucket, key) {
    const row = this.auth.prepare('SELECT encrypted_value FROM secrets WHERE tenant_id=? AND bucket=? AND item_key=?')
      .get(safeTenantId(tenantValue), bucket, key);
    return row ? this.codec.decrypt(row.encrypted_value) : null;
  }

  deleteSecrets(tenantValue, bucket = null) {
    const tenant = safeTenantId(tenantValue);
    if (bucket) this.auth.prepare('DELETE FROM secrets WHERE tenant_id=? AND bucket=?').run(tenant, bucket);
    else this.auth.prepare('DELETE FROM secrets WHERE tenant_id=?').run(tenant);
  }

  configureCloud(tenant, config) {
    for (const [key, value] of Object.entries(config)) {
      if (value) this.setSecret(tenant, 'cloud', key, String(value));
    }
  }

  getCloud(tenant) {
    const keys = ['access_token', 'phone_number_id', 'business_account_id', 'api_version', 'app_secret', 'verify_token'];
    return Object.fromEntries(keys.map((key) => [key, this.getSecret(tenant, 'cloud', key) || '']));
  }

  async baileysAuthState(tenantValue) {
    const tenant = safeTenantId(tenantValue);
    const decode = (value) => value ? JSON.parse(value, BufferJSON.reviver) : null;
    const encode = (value) => JSON.stringify(value, BufferJSON.replacer);
    const creds = decode(this.getSecret(tenant, 'baileys', 'creds')) || initAuthCreds();
    return {
      state: {
        creds,
        keys: {
          get: async (type, ids) => Object.fromEntries(ids.map((id) => {
            let value = decode(this.getSecret(tenant, `baileys:${type}`, id));
            if (type === 'app-state-sync-key' && value) value = proto.Message.AppStateSyncKeyData.fromObject(value);
            return [id, value];
          })),
          set: async (data) => {
            this.auth.exec('BEGIN IMMEDIATE');
            try {
              for (const [category, entries] of Object.entries(data)) {
                for (const [id, value] of Object.entries(entries)) {
                  if (value) this.setSecret(tenant, `baileys:${category}`, id, encode(value));
                  else this.auth.prepare('DELETE FROM secrets WHERE tenant_id=? AND bucket=? AND item_key=?').run(tenant, `baileys:${category}`, id);
                }
              }
              this.auth.exec('COMMIT');
            } catch (error) {
              this.auth.exec('ROLLBACK');
              throw error;
            }
          },
        },
      },
      saveCreds: async () => this.setSecret(tenant, 'baileys', 'creds', encode(creds)),
    };
  }

  hasBaileysAuth(tenant) {
    return Boolean(this.getSecret(tenant, 'baileys', 'creds'));
  }

  tenantsWithBucket(bucket) {
    return this.auth.prepare('SELECT DISTINCT tenant_id FROM secrets WHERE bucket=? ORDER BY tenant_id')
      .all(bucket).map((row) => row.tenant_id);
  }

  getJob(key) {
    return this.state.prepare('SELECT * FROM jobs WHERE idempotency_key=?').get(String(key));
  }

  updateJob({ idempotencyKey, tenant, status, result = {}, incrementAttempt = false }) {
    const now = new Date().toISOString();
    this.state.prepare(`INSERT INTO jobs (idempotency_key, tenant_id, status, attempt_count, result_json, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(idempotency_key) DO UPDATE SET status=excluded.status,
      attempt_count=jobs.attempt_count + excluded.attempt_count, result_json=excluded.result_json, updated_at=excluded.updated_at`)
      .run(String(idempotencyKey), safeTenantId(tenant), status, incrementAttempt ? 1 : 0, JSON.stringify(result), now, now);
  }

  addMessage(messageId, tenant, idempotencyKey) {
    this.state.prepare('INSERT OR REPLACE INTO provider_messages VALUES (?, ?, ?)')
      .run(String(messageId), safeTenantId(tenant), String(idempotencyKey));
  }

  jobForMessage(messageId) {
    return this.state.prepare('SELECT * FROM provider_messages WHERE message_id=?').get(String(messageId));
  }

  addEvent(tenant, idempotencyKey, status, message = '') {
    this.state.prepare('INSERT INTO events (tenant_id, idempotency_key, status, message, created_at) VALUES (?, ?, ?, ?, ?)')
      .run(safeTenantId(tenant), String(idempotencyKey), status, String(message).slice(0, 500), new Date().toISOString());
  }

  eventsAfter(tenant, afterId = 0) {
    return this.state.prepare('SELECT id, idempotency_key, status, message, created_at FROM events WHERE tenant_id=? AND id>? ORDER BY id LIMIT 200')
      .all(safeTenantId(tenant), Number(afterId) || 0);
  }

  close() {
    this.auth.close();
    this.state.close();
  }
}
