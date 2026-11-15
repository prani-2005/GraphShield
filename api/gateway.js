// Public Vercel gateway to the separately hosted GraphShield FastAPI service.
// Configure GRAPHSHIELD_BACKEND_URL (HTTPS origin) in Vercel Project Settings.
// Optional: GRAPHSHIELD_ADMIN_TOKEN is attached server-side ONLY to /api/demo/reset.
// The token never reaches browser JavaScript.

const ROUTES = [
  { test: p => p === '/api/health',                  methods: ['GET'] },
  { test: p => p === '/api/diagnostics',             methods: ['GET'] },
  { test: p => ['/api/evidence/mcp-registry', '/api/evidence/datasets', '/api/evidence/infrastructure'].includes(p), methods: ['GET'] },
  { test: p => p === '/api/experiments/learning',    methods: ['GET'] },
  { test: p => p === '/api/benchmarks/dataflow',     methods: ['GET'] },
  { test: p => p === '/api/demo/reset',              methods: ['POST'], reset: true },
  { test: p => p.startsWith('/api/refund-desk/'),    methods: ['GET', 'POST'] },
];

// Best-effort per-instance cooldown for reset. The backend must still enforce its own rate limit.
const RESET_COOLDOWN_MS = 30000;
const lastReset = new Map();

export default async function handler(req, res) {
  const base = (process.env.GRAPHSHIELD_BACKEND_URL || '').trim().replace(/\/$/, '');
  if (!base) {
    res.status(503).json({ detail: 'GraphShield backend not connected. Set GRAPHSHIELD_BACKEND_URL to your public HTTPS FastAPI origin.' });
    return;
  }
  let origin;
  try { origin = new URL(base); } catch { res.status(500).json({ detail: 'Invalid backend URL configuration' }); return; }
  if (origin.protocol !== 'https:' || origin.username || origin.password || origin.search || origin.hash) {
    res.status(500).json({ detail: 'Backend must be a public HTTPS origin without credentials or query parameters' });
    return;
  }

  const path = String(req.query.path || '');
  // Strict shape: no traversal, no encoded characters, no double slashes.
  if (!/^\/api\/[A-Za-z0-9_\-\/]*$/.test(path) || path.includes('..') || path.includes('//')) {
    res.status(404).json({ detail: 'Unknown API route' }); return;
  }
  const route = ROUTES.find(r => r.test(path));
  if (!route) { res.status(404).json({ detail: 'Unknown API route' }); return; }
  if (!route.methods.includes(req.method)) {
    res.setHeader('allow', route.methods.join(', '));
    res.status(405).json({ detail: 'Method not allowed' }); return;
  }

  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim() || 'unknown';
  const headers = { accept: req.headers.accept || 'application/json', 'x-forwarded-for': ip };
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];

  if (route.reset) {
    // This public endpoint is disabled unless intentionally enabled for an isolated, sandbox-only demo.
    if (process.env.GRAPHSHIELD_ENABLE_DEMO_RESET !== 'true') {
      res.status(403).json({ detail: 'Public demo reset is disabled. Configure GRAPHSHIELD_ENABLE_DEMO_RESET=true only for an isolated sandbox.' }); return;
    }
    const token = (process.env.GRAPHSHIELD_ADMIN_TOKEN || '').trim();
    if (!token) {
      res.status(503).json({ detail: 'Demo reset requires the server-side GRAPHSHIELD_ADMIN_TOKEN.' }); return;
    }
    const now = Date.now();
    if (now - (lastReset.get(ip) || 0) < RESET_COOLDOWN_MS) {
      res.setHeader('retry-after', '30');
      res.status(429).json({ detail: 'Reset rate limit reached. Try again in 30 seconds.' }); return;
    }
    lastReset.set(ip, now);
    if (lastReset.size > 500) lastReset.delete(lastReset.keys().next().value);
    headers['x-graphshield-admin'] = token;
  }

  const query = new URLSearchParams(req.query);
  query.delete('path');
  const target = new URL(path, origin);
  target.search = query.toString();

  try {
    const body = ['GET', 'HEAD'].includes(req.method) ? undefined
      : (typeof req.body === 'string' ? req.body : JSON.stringify(req.body ?? {}));
    const reply = await fetch(target, { method: req.method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(180000) });
    res.status(reply.status);
    const contentType = reply.headers.get('content-type');
    if (contentType) res.setHeader('content-type', contentType);
    const retry = reply.headers.get('retry-after'); if (retry) res.setHeader('retry-after', retry);
    res.setHeader('cache-control', 'no-store');
    // Stream SSE/NDJSON so the visible agent trace updates progressively.
    if (reply.body) {
      const reader = reply.body.getReader();
      while (true) { const { done, value } = await reader.read(); if (done) break; res.write(Buffer.from(value)); }
    }
    res.end();
  } catch (err) {
    if (!res.headersSent) res.status(502).json({ detail: 'GraphShield backend unavailable', reason: String(err?.message || err) });
    else res.end();
  }
}
