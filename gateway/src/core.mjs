import crypto from 'node:crypto';

export const MAX_PDF_BYTES = 10 * 1024 * 1024;
export const MAX_PDFS = 5;

export function safeTenantId(value) {
  const tenant = String(value || '').trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9.-]{2,190}$/.test(tenant)) throw new Error('Invalid tenant identifier.');
  return tenant;
}

export function normalizeInternationalNumber(value) {
  let digits = String(value || '').trim().replace(/[\s()+.-]/g, '');
  if (digits.startsWith('00')) digits = digits.slice(2);
  if (!/^\d{8,15}$/.test(digits) || digits.startsWith('0')) {
    throw new Error('Enter a valid international WhatsApp number including the country code.');
  }
  return digits;
}

export function maskNumber(value) {
  const digits = String(value || '').replace(/\D/g, '');
  return digits ? `${'*'.repeat(Math.max(4, digits.length - 4))}${digits.slice(-4)}` : '';
}

export function safeError(error) {
  return String(error?.message || error || 'Unknown WhatsApp error')
    .replace(/(?:Bearer\s+)?[A-Za-z0-9_\-.]{20,}/gi, '[REDACTED]')
    .replace(/(?:token|secret|password|credential|authorization)\s*[=:]\s*[^\s,;]+/gi, '$1=[REDACTED]')
    .slice(0, 500);
}

export function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

export function canonicalSignature({ timestamp, nonce, method, path, body }) {
  return `${timestamp}\n${nonce}\n${String(method).toUpperCase()}\n${path}\n${sha256(body)}`;
}

export function signRequest(secret, request) {
  return crypto.createHmac('sha256', secret).update(canonicalSignature(request)).digest('hex');
}

export function verifyRequest(secret, request, suppliedSignature, now = Date.now()) {
  const timestamp = Number(request.timestamp);
  if (!Number.isFinite(timestamp) || Math.abs(now - timestamp * 1000) > 300_000) return false;
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(String(request.nonce || ''))) return false;
  const expected = Buffer.from(signRequest(secret, request), 'hex');
  let supplied;
  try { supplied = Buffer.from(String(suppliedSignature || ''), 'hex'); } catch (_) { return false; }
  return expected.length === supplied.length && crypto.timingSafeEqual(expected, supplied);
}

export function validatePdfs(pdfs) {
  if (!Array.isArray(pdfs) || pdfs.length > MAX_PDFS) throw new Error(`At most ${MAX_PDFS} PDF documents may be sent together.`);
  return pdfs.map((item) => {
    const filename = String(item?.filename || '').trim();
    if (!filename || filename !== filename.split(/[\\/]/).pop() || !filename.toLowerCase().endsWith('.pdf')) {
      throw new Error('Invalid PDF filename.');
    }
    const content = Buffer.from(String(item?.content_base64 || ''), 'base64');
    if (!content.length || content.length > MAX_PDF_BYTES || content.subarray(0, 5).toString('ascii') !== '%PDF-') {
      throw new Error(`Invalid PDF document: ${filename}`);
    }
    return { filename, content };
  });
}

export function buildTextPayload(to, text) {
  const body = String(text || '').trim();
  if (!body || body.length > 4096) throw new Error('WhatsApp text must contain 1 to 4096 characters.');
  return { messaging_product: 'whatsapp', recipient_type: 'individual', to, type: 'text', text: { preview_url: false, body } };
}

export function buildDocumentPayload(to, mediaId, filename) {
  return { messaging_product: 'whatsapp', recipient_type: 'individual', to, type: 'document', document: { id: mediaId, filename } };
}

export function encryptedCodec(masterSecret) {
  const key = crypto.createHash('sha256').update(masterSecret).digest();
  return {
    encrypt(plainText) {
      const iv = crypto.randomBytes(12);
      const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
      const ciphertext = Buffer.concat([cipher.update(String(plainText), 'utf8'), cipher.final()]);
      return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]).toString('base64');
    },
    decrypt(encoded) {
      const packed = Buffer.from(String(encoded), 'base64');
      const decipher = crypto.createDecipheriv('aes-256-gcm', key, packed.subarray(0, 12));
      decipher.setAuthTag(packed.subarray(12, 28));
      return Buffer.concat([decipher.update(packed.subarray(28)), decipher.final()]).toString('utf8');
    },
  };
}

export class SequentialQueue {
  constructor(delayMs = 10_000) {
    this.delayMs = Math.max(0, Number(delayMs) || 0);
    this.tail = Promise.resolve();
    this.lastStartedAt = 0;
  }

  add(work, delayMs = this.delayMs) {
    const run = async () => {
      const effectiveDelay = Math.max(this.delayMs, Math.min(300_000, Number(delayMs) || this.delayMs));
      const wait = Math.max(0, effectiveDelay - (Date.now() - this.lastStartedAt));
      if (wait) await new Promise((resolve) => setTimeout(resolve, wait));
      this.lastStartedAt = Date.now();
      return work();
    };
    const result = this.tail.then(run, run);
    this.tail = result.catch(() => undefined);
    return result;
  }
}
