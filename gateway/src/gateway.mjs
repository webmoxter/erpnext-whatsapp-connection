import crypto from 'node:crypto';
import pino from 'pino';
import QRCode from 'qrcode';
import makeWASocket, { DisconnectReason, fetchLatestWaWebVersion, jidNormalizedUser } from 'baileys';
import {
  SequentialQueue,
  buildDocumentPayload,
  buildTextPayload,
  maskNumber,
  normalizeInternationalNumber,
  safeError,
  safeTenantId,
  validatePdfs,
} from './core.mjs';

const silentLogger = pino({ level: 'silent' });

function emptyStatus(provider = 'Baileys') {
  return {
    provider,
    status: 'Disconnected',
    connected: false,
    authenticated: false,
    qr_data_url: '',
    qr_generated_at: '',
    last_connected_at: '',
    last_disconnected_at: '',
    last_error: '',
  };
}

function statusKey(tenant, provider) {
  return `${tenant}\u0000${provider}`;
}

export class WhatsAppGateway {
  constructor({ store, throttleMs = 10_000, logger = silentLogger }) {
    this.store = store;
    this.sessions = new Map();
    this.statuses = new Map();
    this.queue = new SequentialQueue(throttleMs);
    this.logger = logger;
  }

  async initialize() {
    for (const tenant of this.store.tenantsWithBucket('baileys')) {
      await this.connect(tenant, 'Baileys').catch((error) => {
        this.setStatus(tenant, 'Error', { provider: 'Baileys', connected: false, last_error: safeError(error) });
      });
    }
    for (const tenant of this.store.tenantsWithBucket('cloud')) {
      await this.testCloud(tenant).catch(() => undefined);
    }
  }

  status(tenantValue, provider = 'Baileys') {
    const tenant = safeTenantId(tenantValue);
    const normalizedProvider = provider === 'Official API' ? 'Official API' : 'Baileys';
    const state = this.statuses.get(statusKey(tenant, normalizedProvider)) || emptyStatus(normalizedProvider);
    return { ...state, auth_storage: 'Private encrypted gateway storage (contents never exposed)' };
  }

  setStatus(tenant, status, update = {}) {
    const provider = update.provider === 'Official API' ? 'Official API' : 'Baileys';
    const key = statusKey(tenant, provider);
    const current = this.statuses.get(key) || emptyStatus(provider);
    const next = { ...current, ...update, status };
    if (status !== 'QR Ready') {
      next.qr_data_url = '';
      next.qr_generated_at = '';
    }
    this.statuses.set(key, next);
    this.logger.info(
      { event: 'connection_status', tenant_id: tenant, provider: next.provider, status, connected: Boolean(next.connected), error: next.last_error || undefined },
      'WhatsApp gateway status changed',
    );
    return this.status(tenant, provider);
  }

  async connect(tenantValue, providerValue) {
    const tenant = safeTenantId(tenantValue);
    const provider = providerValue === 'Official API' ? 'Official API' : 'Baileys';
    if (provider === 'Official API') return this.testCloud(tenant);
    if (this.sessions.get(tenant)?.socket) return this.status(tenant, provider);
    this.setStatus(tenant, 'Connecting', { provider, connected: false, last_error: '' });
    const auth = await this.store.baileysAuthState(tenant);
    let version;
    try { version = (await fetchLatestWaWebVersion({ signal: AbortSignal.timeout(15_000) })).version; } catch (_) {}
    const socket = makeWASocket({
      auth: auth.state,
      ...(version ? { version } : {}),
      logger: silentLogger,
      browser: ['ERPNext WhatsApp Connection by TNGSol.com', 'Chrome', '0.1.2'],
      markOnlineOnConnect: false,
      syncFullHistory: false,
      generateHighQualityLinkPreview: false,
      shouldSyncHistoryMessage: () => false,
      getMessage: async () => undefined,
    });
    const session = { socket, reconnectTimer: null, manualStop: false };
    this.sessions.set(tenant, session);
    socket.ev.on('creds.update', auth.saveCreds);
    socket.ev.on('connection.update', async (update) => {
      if (this.sessions.get(tenant) !== session) return;
      if (update.qr) {
        const qr = await QRCode.toDataURL(update.qr, { margin: 2, width: 320, errorCorrectionLevel: 'M' });
        this.setStatus(tenant, 'QR Ready', {
          provider, connected: false, authenticated: false, qr_data_url: qr,
          qr_generated_at: new Date().toISOString(), last_error: '',
        });
      }
      if (update.connection === 'open') {
        this.setStatus(tenant, 'Connected', {
          provider, connected: true, authenticated: true,
          account_number: maskNumber(socket.user?.id || ''), last_connected_at: new Date().toISOString(), last_error: '',
        });
      }
      if (update.connection === 'close') {
        const code = update.lastDisconnect?.error?.output?.statusCode;
        const expired = [DisconnectReason.loggedOut, DisconnectReason.badSession, DisconnectReason.multideviceMismatch].includes(code);
        this.sessions.delete(tenant);
        if (session.manualStop) return;
        if (expired) {
          this.setStatus(tenant, 'Authentication expired', { provider, connected: false, authenticated: false, last_error: safeError(update.lastDisconnect?.error) });
        } else {
          this.setStatus(tenant, 'Reconnecting', { provider, connected: false, last_error: safeError(update.lastDisconnect?.error) });
          session.reconnectTimer = setTimeout(() => this.connect(tenant, provider).catch((error) => {
            this.setStatus(tenant, 'Error', { provider, connected: false, last_error: safeError(error) });
          }), 10_000);
        }
      }
    });
    socket.ev.on('messages.update', (updates) => {
      for (const item of updates || []) {
        const messageId = item?.key?.id;
        const status = Number(item?.update?.status || 0);
        const job = messageId ? this.store.jobForMessage(messageId) : null;
        if (job && status >= 2) this.store.addEvent(job.tenant_id, job.idempotency_key, 'Acknowledged by WhatsApp');
      }
    });
    return this.status(tenant, provider);
  }

  async disconnect(tenantValue, providerValue = 'Baileys') {
    const tenant = safeTenantId(tenantValue);
    const session = this.sessions.get(tenant);
    if (session) {
      session.manualStop = true;
      if (session.reconnectTimer) clearTimeout(session.reconnectTimer);
      try { await session.socket.logout('Site administrator removed the linked device'); }
      catch (_) { try { session.socket.end(new Error('Administrator unlink')); } catch (_) {} }
      this.sessions.delete(tenant);
    }
    this.store.deleteSecrets(tenant);
    return this.setStatus(tenant, 'Disconnected', {
      provider: providerValue === 'Official API' ? 'Official API' : 'Baileys', connected: false, authenticated: false,
      last_disconnected_at: new Date().toISOString(), last_error: '',
    });
  }

  async configureCloud(tenantValue, config) {
    const tenant = safeTenantId(tenantValue);
    const apiVersion = String(config.api_version || 'v26.0');
    if (!/^v\d+\.\d+$/.test(apiVersion)) throw new Error('Invalid Meta Graph API version.');
    if (!/^\d{5,30}$/.test(String(config.phone_number_id || ''))) throw new Error('Invalid WhatsApp phone number ID.');
    if (!String(config.access_token || '').trim()) throw new Error('The official API access token is required.');
    if (String(config.app_secret || '').trim().length < 16) throw new Error('A valid Meta app secret is required.');
    if (String(config.verify_token || '').trim().length < 16) throw new Error('Use a webhook verification token of at least 16 characters.');
    this.store.configureCloud(tenant, { ...config, api_version: apiVersion });
    return this.testCloud(tenant);
  }

  async cloudRequest(tenant, path, options = {}) {
    const config = this.store.getCloud(tenant);
    if (!config.access_token || !config.phone_number_id) throw new Error('Official WhatsApp Business API credentials are not configured.');
    const response = await fetch(`https://graph.facebook.com/${config.api_version || 'v26.0'}/${path}`, {
      ...options,
      headers: { Authorization: `Bearer ${config.access_token}`, ...(options.headers || {}) },
      signal: AbortSignal.timeout(30_000),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Official WhatsApp API request failed (HTTP ${response.status}): ${safeError(data?.error?.message || 'Request rejected')}`);
    return data;
  }

  async testCloud(tenantValue) {
    const tenant = safeTenantId(tenantValue);
    this.setStatus(tenant, 'Connecting', { provider: 'Official API', connected: false, last_error: '' });
    try {
      const config = this.store.getCloud(tenant);
      await this.cloudRequest(tenant, `${config.phone_number_id}?fields=display_phone_number,verified_name,quality_rating`);
      return this.setStatus(tenant, 'Connected', {
        provider: 'Official API', connected: true, authenticated: true,
        last_connected_at: new Date().toISOString(), last_error: '',
      });
    } catch (error) {
      return this.setStatus(tenant, 'Error', { provider: 'Official API', connected: false, authenticated: false, last_error: safeError(error) });
    }
  }

  async sendCloud(tenant, number, text, pdfs) {
    const config = this.store.getCloud(tenant);
    const ids = [];
    for (const pdf of pdfs) {
      const form = new FormData();
      form.append('messaging_product', 'whatsapp');
      form.append('type', 'application/pdf');
      form.append('file', new Blob([pdf.content], { type: 'application/pdf' }), pdf.filename);
      const media = await this.cloudRequest(tenant, `${config.phone_number_id}/media`, { method: 'POST', body: form });
      const sent = await this.cloudRequest(tenant, `${config.phone_number_id}/messages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildDocumentPayload(number, media.id, pdf.filename)),
      });
      ids.push(String(sent.messages?.[0]?.id || ''));
    }
    if (text) {
      const sent = await this.cloudRequest(tenant, `${config.phone_number_id}/messages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buildTextPayload(number, text)),
      });
      ids.push(String(sent.messages?.[0]?.id || ''));
    }
    if (!ids.length || ids.some((id) => !id)) throw new Error('Official WhatsApp API did not confirm every submission.');
    return ids;
  }

  async sendBaileys(tenant, number, text, pdfs) {
    if (!this.sessions.get(tenant)?.socket || !this.status(tenant).connected) await this.connect(tenant, 'Baileys');
    const socket = this.sessions.get(tenant)?.socket;
    if (!socket || !this.status(tenant).connected) throw new Error('WhatsApp linked device is not connected.');
    const checked = await socket.onWhatsApp(`${number}@s.whatsapp.net`);
    const registered = checked?.find((entry) => entry.exists === true);
    if (!registered) throw new Error('This number is not registered on WhatsApp. Nothing was sent.');
    const jid = jidNormalizedUser(registered.jid);
    const ids = [];
    for (const pdf of pdfs) {
      const sent = await socket.sendMessage(jid, { document: pdf.content, mimetype: 'application/pdf', fileName: pdf.filename });
      ids.push(String(sent?.key?.id || ''));
    }
    if (text) {
      const sent = await socket.sendMessage(jid, { text });
      ids.push(String(sent?.key?.id || ''));
    }
    if (!ids.length || ids.some((id) => !id)) throw new Error('WhatsApp did not confirm every submission.');
    return ids;
  }

  send(request) {
    const requestedThrottle = Math.max(10_000, Math.min(300_000, Number(request.throttle_ms) || this.queue.delayMs));
    return this.queue.add(async () => {
      const tenant = safeTenantId(request.tenant_id);
      const key = String(request.idempotency_key || '').trim();
      if (!/^[A-Za-z0-9_.:-]{16,190}$/.test(key)) throw new Error('Invalid idempotency key.');
      const existing = this.store.getJob(key);
      if (existing && ['Submitted to WhatsApp', 'Acknowledged by WhatsApp'].includes(existing.status)) {
        return { ...JSON.parse(existing.result_json), replayed: true };
      }
      const number = normalizeInternationalNumber(request.recipient);
      const text = String(request.text || '').trim();
      const pdfs = validatePdfs(request.pdfs || []);
      if (!text && !pdfs.length) throw new Error('A text message or PDF document is required.');
      if (text) buildTextPayload(number, text);
      this.store.updateJob({ idempotencyKey: key, tenant, status: 'Queued', incrementAttempt: true });
      try {
        const provider = request.provider === 'Official API' ? 'Official API' : 'Baileys';
        const messageIds = provider === 'Official API'
          ? await this.sendCloud(tenant, number, text, pdfs)
          : await this.sendBaileys(tenant, number, text, pdfs);
        const result = { success: true, provider, message_ids: messageIds, recipient_masked: maskNumber(number), submitted_at: new Date().toISOString() };
        this.store.updateJob({ idempotencyKey: key, tenant, status: 'Submitted to WhatsApp', result });
        messageIds.forEach((id) => this.store.addMessage(id, tenant, key));
        this.store.addEvent(tenant, key, 'Submitted to WhatsApp');
        return result;
      } catch (error) {
        const message = safeError(error);
        this.store.updateJob({ idempotencyKey: key, tenant, status: 'Failed', result: { success: false, message } });
        this.store.addEvent(tenant, key, 'Failed', message);
        throw new Error(message);
      }
    }, requestedThrottle);
  }

  verifyCloudWebhook(tenantValue, token, challenge) {
    const config = this.store.getCloud(safeTenantId(tenantValue));
    const expected = Buffer.from(config.verify_token || '');
    const supplied = Buffer.from(String(token || ''));
    if (!expected.length || expected.length !== supplied.length || !crypto.timingSafeEqual(expected, supplied)) {
      throw new Error('Webhook verification failed.');
    }
    return String(challenge || '');
  }

  receiveCloudWebhook(tenantValue, rawBody, signature) {
    const tenant = safeTenantId(tenantValue);
    const config = this.store.getCloud(tenant);
    const expected = `sha256=${crypto.createHmac('sha256', config.app_secret).update(rawBody).digest('hex')}`;
    const supplied = String(signature || '');
    if (!config.app_secret || expected.length !== supplied.length || !crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(supplied))) {
      throw new Error('Invalid Meta webhook signature.');
    }
    const payload = JSON.parse(rawBody);
    let accepted = 0;
    for (const entry of payload.entry || []) for (const change of entry.changes || []) {
      for (const status of change.value?.statuses || []) {
        const job = this.store.jobForMessage(status.id);
        if (!job || job.tenant_id !== tenant) continue;
        const next = status.status === 'failed' ? 'Failed' : 'Acknowledged by WhatsApp';
        const message = status.status === 'failed' ? safeError(status.errors?.[0]?.title || 'Official API delivery failed') : '';
        this.store.addEvent(tenant, job.idempotency_key, next, message);
        accepted += 1;
      }
    }
    return { accepted };
  }
}
