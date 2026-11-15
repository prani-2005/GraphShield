'use strict';
/* GraphShield V9 · UI layer.
   Everything rendered here comes from real backend responses. If an endpoint is
   missing or a run has not been executed, the UI says so; it never invents numbers. */
(() => {
const $ = id => document.getElementById(id);
const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const pct = (v, d = 1) => v == null ? 'n/a' : (100 * v).toFixed(d) + '%';
const num = (v, d = 2) => v == null || Number.isNaN(+v) ? 'n/a' : (+v).toFixed(d);

/* ---------------- API helper ---------------- */
async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const raw = await r.text();
  let body = null;
  try { body = raw ? JSON.parse(raw) : null; } catch { /* non-JSON */ }
  if (!r.ok) {
    const d = body && (body.detail ?? body.message);
    const msg = r.status === 429 ? 'Rate limit reached. Wait a few seconds and retry.'
      : r.status === 404 ? 'Endpoint not found on the backend (' + path + '). The backend must implement it.'
      : r.status === 503 ? 'Backend not connected. Set GRAPHSHIELD_BACKEND_URL on Vercel.'
      : (typeof d === 'string' ? d : d ? JSON.stringify(d) : 'HTTP ' + r.status);
    const e = new Error(msg); e.status = r.status; throw e;
  }
  if (body === null) throw new Error('Backend returned a non-JSON response for ' + path);
  return body;
}
const val = v => v == null ? null : (typeof v === 'number' ? v : (v.mean ?? null));
const spread = v => (v == null || typeof v === 'number') ? 0 : (v.std ?? ((v.max != null && v.min != null) ? (v.max - v.min) / 2 : 0));

function toast(msg, bad = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => t.remove(), 4500);
}
async function withBusy(btn, fn) {
  if (!btn || btn.classList.contains('busy')) return;
  btn.classList.add('busy');
  try { return await fn(); } finally { btn.classList.remove('busy'); }
}
function countUp(el, to, { dec = 0, suffix = '', ms = 900 } = {}) {
  if (to == null || Number.isNaN(+to)) { el.textContent = 'n/a'; return; }
  if (reduceMotion) { el.textContent = (+to).toFixed(dec) + suffix; return; }
  const t0 = performance.now();
  const step = t => {
    const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = (to * e).toFixed(dec) + suffix;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
function armBars(root) {
  requestAnimationFrame(() => requestAnimationFrame(() => {
    root.querySelectorAll('[data-w]').forEach(el => { el.style.width = el.dataset.w + '%'; });
  }));
}
function armLines(root) {
  root.querySelectorAll('.chart-line').forEach(p => {
    try { p.style.setProperty('--len', Math.ceil(p.getTotalLength()) + 2); } catch { /* ignore */ }
  });
}

/* ---------------- hero: animated graph backdrop ---------------- */
function network() {
  const hero = document.querySelector('.hero');
  if (!hero) return;
  const c = document.createElement('canvas'); c.id = 'netBg'; c.setAttribute('aria-hidden', 'true');
  hero.prepend(c);
  const g = c.getContext('2d');
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  let W = 0, H = 0, nodes = [], raf = 0, visible = true, t = 0;
  function size() {
    const b = hero.getBoundingClientRect(); W = b.width; H = b.height;
    c.width = W * dpr; c.height = H * dpr; g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(48, Math.max(14, W * H / 14000)));
    nodes = Array.from({ length: n }, () => ({
      x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .28, vy: (Math.random() - .5) * .28,
      r: 1.4 + Math.random() * 1.9, hub: Math.random() < .16
    }));
  }
  function draw() {
    g.clearRect(0, 0, W, H); t += .016;
    for (const a of nodes) {
      a.x += a.vx; a.y += a.vy;
      if (a.x < 0 || a.x > W) a.vx *= -1; if (a.y < 0 || a.y > H) a.vy *= -1;
    }
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < 140) {
        const al = (1 - d / 140) * .35;
        g.strokeStyle = `rgba(71,213,184,${al})`; g.lineWidth = 1;
        g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
        if ((a.hub || b.hub) && !reduceMotion) {      // traveling "query" pulse along hub edges
          const k = (t * .5 + i * .13) % 1;
          g.fillStyle = 'rgba(165,139,255,.85)';
          g.beginPath(); g.arc(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k, 1.8, 0, 6.3); g.fill();
        }
      }
    }
    for (const a of nodes) {
      g.fillStyle = a.hub ? 'rgba(165,139,255,.95)' : 'rgba(124,240,216,.8)';
      g.beginPath(); g.arc(a.x, a.y, a.hub ? a.r + 1.2 : a.r, 0, 6.3); g.fill();
    }
  }
  function loop() { if (visible && !document.hidden) draw(); raf = requestAnimationFrame(loop); }
  size(); draw();
  if (!reduceMotion) loop();
  addEventListener('resize', () => { size(); draw(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(e => { visible = e[0].isIntersecting; }).observe(hero);
}

/* ---------------- reveal + scroll-spy ---------------- */
function reveals() {
  const els = [...document.querySelectorAll('.panel,.case-card')];
  if (!('IntersectionObserver' in window)) return;
  els.forEach(el => el.classList.add('reveal'));
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .06 });
  els.forEach(el => io.observe(el));
}
function spy() {
  const btns = [...document.querySelectorAll('[data-jump]')];
  const secs = btns.map(b => ({ b, el: $(b.dataset.jump) })).filter(x => x.el);
  let tick = false;
  const update = () => {
    tick = false;
    const y = innerHeight * .35;
    // among sections crossing the reading line, prefer the left-most (panels can sit side by side)
    const hit = secs.map(s => ({ ...s, r: s.el.getBoundingClientRect() })).filter(s => s.r.top <= y && s.r.bottom >= y && s.el.id !== 'deskTop');
    const pick = hit.sort((p, q) => p.r.left - q.r.left)[0] || secs[0];
    btns.forEach(x => x.classList.toggle('active', x === pick.b));
  };
  addEventListener('scroll', () => { if (!tick) { tick = true; requestAnimationFrame(update); } }, { passive: true });
  update();
}

/* ---------------- charts ---------------- */
const SYS = {
  preload_all_oracle: { color: '#7c8fa6', label: 'Preload-all oracle (not real LLM)' },
  static_primary:    { color: '#7c8fa6', label: 'Static router (always primary)' },
  lexical_topk:      { color: '#7aaee7', label: 'Lexical top-k (keyword match, not vector search)' },
  graphshield_cold:  { color: '#e4b56b', label: 'GraphShield cold (learning off)' },
  graphshield_learned: { color: '#47d5b8', label: 'GraphShield learned' }
};
const sysStyle = (k, i) => SYS[k] || { color: ['#a58bff', '#ff9b9e', '#9bd36b', '#f0a'][i % 4], label: k };

function lineChart({ series, xs, xLabel, yLabel, fmt }) {
  const W = 680, H = 310, L = 58, R = 16, T = 14, B = 54;
  let lo = Infinity, hi = -Infinity;
  for (const s of series) for (const p of s.pts) if (p.m != null) { lo = Math.min(lo, p.m - p.s); hi = Math.max(hi, p.m + p.s); }
  if (!isFinite(lo)) return '<div class="empty">No numeric data for this metric in the response.</div>';
  const pad = (hi - lo) * .12 || Math.abs(hi) * .1 || 1;
  lo = lo >= 0 ? Math.max(0, lo - pad) : lo - pad; hi += pad;
  const X = i => L + i * (W - L - R) / Math.max(1, xs.length - 1);
  const Y = v => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  let grid = '<g class="chart-grid">';
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4;
    grid += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 7}" y="${Y(v) + 4}" text-anchor="end" fill="#93a8bb">${esc(fmt(v))}</text>`;
  }
  grid += '</g>';
  xs.forEach((x, i) => { grid += `<text x="${X(i)}" y="${H - B + 17}" text-anchor="middle" fill="#93a8bb">${esc(x)}</text>`; });
  grid += `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle" fill="#93a8bb">${esc(xLabel)}</text>`;
  grid += `<text transform="translate(13 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="#93a8bb">${esc(yLabel)}</text>`;
  let body = '';
  series.forEach(s => {
    const pts = s.pts.map((p, i) => ({ ...p, i })).filter(p => p.m != null);
    if (!pts.length) return;
    if (pts.some(p => p.s > 0)) {
      const up = pts.map(p => `${X(p.i)},${Y(p.m + p.s)}`).join(' L');
      const dn = [...pts].reverse().map(p => `${X(p.i)},${Y(p.m - p.s)}`).join(' L');
      body += `<path class="chart-band" d="M${up} L${dn}Z" fill="${s.color}" opacity="0"/>`;
    }
    const w = s.hero ? 3.4 : 2;
    body += `<polyline class="chart-line" fill="none" stroke="${s.color}" stroke-width="${w}" stroke-linejoin="round" points="${pts.map(p => `${X(p.i)},${Y(p.m)}`).join(' ')}"/>`;
    pts.forEach(p => { body += `<circle class="chart-dot" cx="${X(p.i)}" cy="${Y(p.m)}" r="${s.hero ? 4.4 : 3.2}" fill="${s.color}"><title>${esc(s.label)} · ${esc(xs[p.i])}: ${esc(fmt(p.m))} ± ${esc(fmt(p.s))}</title></circle>`; });
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yLabel)} by iteration for each system">${grid}${body}</svg>`;
}

/* ---------------- Learning study ---------------- */
const METRICS = [
  { key: 'task_success',            label: 'First-try success (injected)',      fmt: v => (100 * v).toFixed(0) + '%', pctScale: true, better: 'high' },
  { key: 'failed_attempts_per_task', label: 'Injected provider failures',   fmt: v => v.toFixed(2), better: 'low' },
  { key: 'round_trips_per_task',    label: 'Model round-trips (unmeasured)',       fmt: v => v.toFixed(2), better: 'low' },
  { key: 'tokens_per_task',         label: 'Schema tokens (estimated)',            fmt: v => Math.round(v).toLocaleString(), better: 'low', tokens: true },
  { key: 'p95_latency_ms',          label: 'p95 latency (unmeasured)',  fmt: v => Math.round(v) + ' ms', better: 'low' }
];
let learning = null, metricKey = 'task_success';

function tokenTag(d) {
  const b = String(d.tokens_basis || '').toLowerCase();
  if (b === 'measured') return '<span class="tag measured">Tokens: Measured</span>';
  if (b === 'estimated') return '<span class="tag estimated">Tokens: Estimated</span>';
  return '<span class="tag na">Token basis not stated by backend</span>';
}
function renderLearning() {
  const out = $('labLearningOut'), d = learning;
  if (!d) return;
  const m = METRICS.find(x => x.key === metricKey);
  const rows = d.summary || [];
  const systems = d.systems || [...new Set(rows.map(r => r.system))];
  const iters = [...new Set(rows.map(r => r.iteration))].sort((a, b) => a - b);
  const series = systems.map((s, i) => {
    const st = sysStyle(s, i);
    return { label: st.label, color: st.color, hero: s === 'graphshield_learned',
      pts: iters.map(it => { const r = rows.find(x => x.system === s && x.iteration === it); const v = r && r[m.key]; return { m: val(v), s: spread(v) }; }) };
  });
  const fmt = m.fmt;
  const prov = (d.providers || []).map(p => `<span class="chip">${esc(p.name)} · ${num((p.failure_rate ?? NaN) * 100, 0)}% fail · ${esc(p.latency_ms)} ms</span>`).join('');
  const last = iters[iters.length - 1];
  const finalRows = systems.map((s, i) => {
    const r = rows.find(x => x.system === s && x.iteration === last) || {};
    const st = sysStyle(s, i);
    return `<tr><td><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${st.color};margin-right:7px"></i>${esc(st.label)}</td>` +
      METRICS.map(mm => { const v = r[mm.key]; return `<td>${val(v) == null ? 'n/a' : esc(mm.fmt(val(v)))} <span class="muted">± ${val(v) == null ? 'n/a' : esc(mm.fmt(spread(v)))}</span></td>`; }).join('') + '</tr>';
  }).join('');

  // honest verdict computed from the data: learned vs best baseline at final iteration
  let verdict = '';
  const learnedS = series.find(s => s.hero);
  if (learnedS) {
    const li = iters.length - 1, L = learnedS.pts[li];
    const others = series.filter(s => !s.hero && s.pts[li] && s.pts[li].m != null);
    if (L && L.m != null && others.length) {
      const best = others.reduce((a, b) => (m.better === 'high' ? (b.pts[li].m > a.pts[li].m) : (b.pts[li].m < a.pts[li].m)) ? b : a);
      const B = best.pts[li], diff = L.m - B.m;
      const improved = m.better === 'high' ? diff > 0 : diff < 0;
      const within = Math.abs(diff) <= Math.max(L.s, B.s);
      const cls = within ? 'warn' : improved ? 'good' : 'bad';
      const text = within
        ? `Difference vs the best baseline is <strong>within seed spread</strong>; this is not a clear win on this metric.`
        : improved ? `Learned beats the best baseline by <strong>${esc(fmt(Math.abs(diff)))}</strong> on ${esc(m.label.toLowerCase())}, outside seed spread.`
        : `Learned is <strong>worse</strong> than the best baseline by ${esc(fmt(Math.abs(diff)))} on ${esc(m.label.toLowerCase())}.`;
      verdict = `<div class="verdict ${cls}">Final iteration, held-out set · best baseline: ${esc(best.label)}. ${text}</div>`;
    }
  }
  const split = d.split ? ` · ${esc(d.split.train)} train / ${esc(d.split.held_out)} held-out cases` : '';
  out.innerHTML =
    `<div class="flex wrap" style="margin:4px 0 8px"><span class="tag sim">Simulated fault injection</span>${tokenTag(d)}<span class="tiny muted">backend: ${esc(d.backend || 'unspecified')} · ${esc((d.seeds || []).length)} seeds · ${esc(iters.length)} iterations${split}</span></div>` +
    (prov ? `<div class="chips" style="margin:8px 0">${prov}</div>` : '') +
    `<div class="chart-card">${lineChart({ series, xs: iters.map(i => 'iter ' + i), xLabel: 'Learning iteration (evaluated on held-out set; band = seed spread)', yLabel: m.label, fmt })}` +
    `<div class="legend big">${series.map(s => `<span><i style="background:${s.color}"></i>${esc(s.label)}</span>`).join('')}</div></div>` +
    verdict +
    `<div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>System @ final iteration</th>${METRICS.map(mm => `<th>${esc(mm.label)}</th>`).join('')}</tr></thead><tbody>${finalRows}</tbody></table></div>` +
    ((d.limitations || []).length ? `<div class="disclosure">${esc(d.limitations.join(' · '))}</div>` : '') +
    (d.citable_as_hydradb_evidence === false ? '<div class="status bad">Not HydraDB evidence: this run used a non-HydraDB backend.</div>' : '');
  armLines(out);
}
function buildSeg() {
  const seg = $('labMetricSeg'); if (!seg) return;
  seg.innerHTML = METRICS.map(m => `<button data-m="${m.key}" class="${m.key === metricKey ? 'active' : ''}">${esc(m.label)}</button>`).join('');
  seg.onclick = e => { const b = e.target.closest('button[data-m]'); if (!b) return; metricKey = b.dataset.m; seg.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); renderLearning(); };
}
async function loadLearning() {
  const out = $('labLearningOut');
  out.innerHTML = '<div class="skeleton"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:60%"></div>';
  try { learning = await api('/api/experiments/learning'); renderLearning(); }
  catch (e) { learning = null; out.innerHTML = `<div class="status bad">No learning results: ${esc(e.message)}</div><div class="tiny muted">Run the experiment on the backend first, then reload. The UI shows only saved results.</div>`; }
}

/* ---------------- Benchmarks (dataflow edges + ablation) ---------------- */
function barRow(label, v, max, cls, text) {
  const w = max > 0 && v != null ? Math.max(1.5, 100 * v / max) : 0;
  return `<div class="bar-row"><span>${esc(label)}</span><div class="bar-track"><div class="bar-fill ${cls}" data-w="${w.toFixed(1)}"></div></div><strong>${esc(text)}</strong></div>`;
}
function renderBench(d) {
  const out = $('benchOut');
  const reg = d.registry || {}, df = d.dataflow_edges || {}, hc = df.hand_check || {}, mh = d.multi_hop || {};
  const edges = d.sample_edges || [];
  const checked = edges.filter(e => e.hand_check === 'correct' || e.hand_check === 'incorrect');
  const prec = hc.precision ?? (checked.length ? checked.filter(e => e.hand_check === 'correct').length / checked.length : null);
  const precN = hc.sampled ?? checked.length;
  const tb = String(reg.tokens_basis || '').toLowerCase();
  const kp = (label, v, sub, opt = {}) => `<div class="kpi"><div class="label">${esc(label)}</div><div class="number" data-count="${v == null ? '' : v}" data-dec="${opt.dec || 0}" data-suf="${esc(opt.suf || '')}">${v == null ? 'n/a' : '0'}</div><div class="sub">${sub}</div></div>`;
  const sys = mh.systems || [];
  const groups = [
    { t: 'Dependency recall (higher is better)', k: 'dependency_recall', pctv: true },
    { t: 'Plan correctness (higher is better)', k: 'plan_correctness', pctv: true },
    { t: 'HydraDB / store queries per case (lower is better)', k: 'queries_per_case', pctv: false }
  ].map(g => {
    const max = g.pctv ? 1 : Math.max(0, ...sys.map(s => s[g.k] ?? 0));
    return `<div class="bar-group"><h3>${esc(g.t)}</h3>` + sys.map(s => barRow(s.label || s.system, s[g.k], max, /flat/i.test(s.system) ? 'flat' : '', g.pctv ? pct(s[g.k]) : num(s[g.k], 2))).join('') + '</div>';
  }).join('');
  const plan = (d.example_plan || []).map((s, i) => `<div class="plan-step"><div class="plan-dot" style="animation-delay:${i * .12}s">${i + 1}</div><div class="plan-body" style="animation-delay:${i * .12}s"><strong>${esc(s.tool)}</strong><div class="io">consumes <b>${esc((s.consumes || []).join(', ') || 'none')}</b> → produces <b>${esc((s.produces || []).join(', ') || 'none')}</b></div></div></div>`).join('');
  const srcs = (reg.distractor_sources || []).map(s => `<tr><td>${esc(s.name)}</td><td>${esc(s.license || 'unknown')}</td><td>${esc(s.count)}</td></tr>`).join('');
  const edgeRows = edges.map(e => {
    const c = e.confidence;
    const v = e.hand_check === 'correct' ? '<span class="tag ok">correct</span>' : e.hand_check === 'incorrect' ? '<span class="tag no">incorrect</span>' : '<span class="tag na">unchecked</span>';
    return `<tr><td class="mono">${esc(e.tool)}</td><td class="mono">${esc(e.relation)}</td><td class="mono">${esc(e.datatype)}</td><td><span class="conf"><span><i data-w="${c == null ? 0 : (100 * c).toFixed(0)}"></i></span>${esc(num(c))}</span></td><td>${v}</td></tr>`;
  }).join('');
  out.innerHTML =
    `<div class="flex wrap"><span class="tag sim">Registry includes distractor tools</span>${tb === 'measured' ? '<span class="tag measured">Tokens: Measured</span>' : tb === 'estimated' ? '<span class="tag estimated">Tokens: Estimated</span>' : '<span class="tag na">Token basis not stated</span>'}</div>` +
    `<div class="mini-kpis">` +
      kp('Registry tools', reg.total_tools, `${esc(reg.real_tools ?? '?')} real + ${esc(reg.distractor_tools ?? '?')} distractors`) +
      kp('Preload-all schema tokens', reg.preload_all_tokens, 'what a preload-everything agent would carry') +
      kp('Candidate dataflow links', df.produces ?? null, 'Unreviewed schema-compatible candidates (not persisted graph edges)') +
      kp('Mean edge confidence', df.mean_confidence, 'inferred from tool schemas', { dec: 2 }) +
      kp('Hand-check precision', prec == null ? null : prec * 100, `${esc(hc.correct ?? checked.filter(e => e.hand_check === 'correct').length)} / ${esc(precN || '?')} sampled edges`, { dec: 1, suf: '%' }) +
    `</div>` +
    `<div class="two-col"><div><h3 style="margin-bottom:6px">Ablation · graph walk vs flat store (multi-hop, ${esc(mh.cases ?? '?')} cases)</h3><p class="tiny muted">Flat store: same registry in a plain dictionary, similarity match only, no traversal.</p>${groups || '<div class="empty">No multi-hop results in the response.</div>'}</div>` +
    `<div><h3 style="margin-bottom:6px">Plan derived by walking edges backward from the goal</h3>${plan || '<div class="empty">Backend did not return an example plan.</div>'}` +
    (srcs ? `<h3 style="margin:18px 0 6px">Distractor sources and licenses</h3><div class="table-wrap"><table><thead><tr><th>Source</th><th>License</th><th>Tools</th></tr></thead><tbody>${srcs}</tbody></table></div>` : '') + `</div></div>` +
    `<h3 style="margin:20px 0 6px">Sampled inferred edges (hand-checked)</h3><div class="table-wrap scroll"><table><thead><tr><th>Tool</th><th>Relation</th><th>DataType</th><th>Confidence</th><th>Hand check</th></tr></thead><tbody>${edgeRows || '<tr><td colspan="5" class="muted">No sampled edges returned.</td></tr>'}</tbody></table></div>` +
    ((d.limitations || []).length ? `<div class="disclosure">${esc(d.limitations.join(' · '))}</div>` : '');
  out.querySelectorAll('[data-count]').forEach(el => { if (el.dataset.count !== '') countUp(el, +el.dataset.count, { dec: +el.dataset.dec, suffix: el.dataset.suf }); });
  armBars(out);
}
async function loadBench() {
  const out = $('benchOut');
  out.innerHTML = '<div class="skeleton"></div><div class="skeleton" style="width:75%"></div>';
  try { renderBench(await api('/api/benchmarks/dataflow')); }
  catch (e) { out.innerHTML = `<div class="status bad">No benchmark results: ${esc(e.message)}</div>`; }
}

/* ---------------- Diagnostics + health + reset ---------------- */
function renderDiag(d) {
  const checks = d.checks || [];
  const ok = d.passed ?? checks.filter(c => c.ok).length, total = d.total ?? checks.length;
  const p = total ? Math.round(100 * ok / total) : 0;
  const sorted = [...checks].sort((a, b) => (a.ok === b.ok ? 0 : a.ok ? 1 : -1));
  $('diagOut').innerHTML =
    `<div class="diag-summary"><div class="ring" id="diagRing" data-label="${ok}/${total}" style="--p:0"></div><div><strong style="font-size:16px">${ok === total && total ? 'All Cypher shapes pass on the running HydraDB' : ok + ' of ' + total + ' shapes pass'}</strong><div class="tiny muted">Every query shape the app uses was executed live. Failures are listed first.</div></div></div>` +
    `<div class="diag-grid">${sorted.map((c, i) => `<div class="diag-item ${c.ok ? 'ok' : 'fail'}" style="animation-delay:${Math.min(i, 24) * 30}ms"><div class="t"><span>${esc(c.name)}</span><span class="tag ${c.ok ? 'ok' : 'no'}">${c.ok ? 'pass' : 'fail'}${c.ms != null ? ' · ' + esc(Math.round(c.ms)) + ' ms' : ''}</span></div>${c.query_shape ? `<code>${esc(c.query_shape)}</code>` : ''}${c.error ? `<div class="err">${esc(c.error)}</div>` : ''}</div>`).join('')}</div>`;
  requestAnimationFrame(() => requestAnimationFrame(() => { const r = $('diagRing'); if (r) r.style.setProperty('--p', p); }));
}
async function runDiag() {
  const out = $('diagOut');
  out.innerHTML = '<div class="skeleton"></div><div class="skeleton" style="width:70%"></div>';
  try { renderDiag(await api('/api/diagnostics')); }
  catch (e) { out.innerHTML = `<div class="status bad">Diagnostics unavailable: ${esc(e.message)}</div>`; }
}
async function loadHealth() {
  const box = $('healthOut'); if (!box) return;
  try {
    const h = await api('/api/health');
    const items = Object.entries(h).filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v));
    box.innerHTML = items.length ? '<dl class="kv">' + items.map(([k, v]) => `<dt>${esc(k.replaceAll('_', ' '))}</dt><dd>${typeof v === 'boolean' ? `<span class="tag ${v ? 'ok' : 'no'}">${v ? 'yes' : 'no'}</span>` : esc(v)}</dd>`).join('') + '</dl>' : '<span class="muted">Backend responded without scalar fields.</span>';
  } catch (e) { box.innerHTML = `<div class="status bad">Health check failed: ${esc(e.message)}</div>`; }
}
async function resetDemo(btn) {
  if (!confirm('Reset the demo? This clears learned provider stats and cached entities in the sandbox graph.')) return;
  await withBusy(btn, async () => {
    try {
      const r = await api('/api/demo/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      toast(r.message || 'Demo reset complete.');
      $('deskTrace')?.replaceChildren(); $('deskGraph')?.replaceChildren();
      $('deskLoadCases')?.click(); loadHealth();
    } catch (e) { toast('Reset failed: ' + e.message, true); }
  });
}

/* ---------------- wire up ---------------- */
function init() {
  network(); reveals(); spy(); buildSeg();
  $('labLoadLearning')?.addEventListener('click', e => withBusy(e.currentTarget, loadLearning));
  $('benchLoad')?.addEventListener('click', e => withBusy(e.currentTarget, loadBench));
  $('diagRun')?.addEventListener('click', e => withBusy(e.currentTarget, async () => { await runDiag(); await loadHealth(); }));
  $('demoReset')?.addEventListener('click', e => resetDemo(e.currentTarget));
  // pulse the status bar whenever its text changes
  const st = $('deskStatus');
  if (st && 'MutationObserver' in window) new MutationObserver(() => { st.classList.remove('pulse'); void st.offsetWidth; st.classList.add('pulse'); }).observe(st, { childList: true, characterData: true, subtree: true });
  loadHealth();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
