# GraphShield V9 — Vercel UI gateway (HydraDB hackathon)

This package is the **browser UI + HTTPS gateway only**. It is not the backend and contains no HydraDB code. A public HTTPS FastAPI backend with a running self-hosted HydraDB (`github.com/hydra-db/hydradb`, Bolt kept private) must exist for anything to work. The UI never fabricates data: a missing endpoint shows an explicit error.

## What changed in V9
- `index.html`: new Benchmarks and Diagnostics sections, 4-system Learning study block, hackathon strip, 8-item nav.
- `static/labs.css` / `static/labs.js` (new): animated graph backdrop, scroll reveals, glowing case card, staged graph-node and trace animations, animated charts (all disabled under `prefers-reduced-motion`).
- `api/gateway.js`: strict allowlist (see below), method checks, reset cooldown, server-side admin token for reset only.
- `vercel.json`: rewrites for the new routes, security headers incl. CSP, `maxDuration` 60 (raise on plans that allow it if SSE traces run longer).
- `static/refund.js`, `static/focused.js`: unchanged.

## Backend contract the new UI expects (implement in FastAPI)
All numeric results must come from real runs. Labels: tokens carry `tokens_basis: "measured" | "estimated"`.

| Route | Method | Response (JSON) |
|---|---|---|
| `/api/health` | GET | scalar fields, e.g. `hydradb_connected`, `seeded` |
| `/api/diagnostics` | GET | `{passed,total,checks:[{name,ok,ms,query_shape,error}]}` — runs every Cypher shape live |
| `/api/experiments/learning` | GET | `{backend,seeds,split:{train,held_out},tokens_basis,providers:[{name,failure_rate,latency_ms}],systems:[static_primary,lexical_topk,graphshield_cold,graphshield_learned],summary:[{system,iteration,task_success,failed_attempts_per_task,round_trips_per_task,tokens_per_task,p95_latency_ms}],limitations:[]}` — each metric is `{mean,std}` (or `{mean,min,max}`) |
| `/api/benchmarks/dataflow` | GET | `{registry:{real_tools,distractor_tools,total_tools,preload_all_tokens,tokens_basis,distractor_sources:[{name,license,count}]},dataflow_edges:{produces,consumes,mean_confidence,hand_check:{sampled,correct,precision}},multi_hop:{cases,systems:[{system,label,dependency_recall,plan_correctness,queries_per_case}]},example_plan:[{tool,consumes,produces}],sample_edges:[{tool,relation,datatype,confidence,hand_check}],limitations:[]}` |
| `/api/demo/reset` | POST | `{message}` — requires `x-graphshield-admin`, rate limited |

The Learning UI computes its win/loss verdict from the data and reports "within seed spread" when the gap is not larger than the spread, so modest gains are shown honestly.

## Deploy
1. Deploy this folder as a Vercel project (Framework Preset: Other).
2. Set env vars in Vercel: `GRAPHSHIELD_BACKEND_URL` (public HTTPS origin, no credentials), and optionally `GRAPHSHIELD_ADMIN_TOKEN` (attached server-side to `/api/demo/reset` only).
3. Public demo reset remains disabled by default. Only if the backend is an isolated disposable sandbox and reset is intentionally public, set `GRAPHSHIELD_ENABLE_DEMO_RESET=true` alongside `GRAPHSHIELD_ADMIN_TOKEN`. A public reset endpoint is not suitable for multi-user production use.
4. Redeploy, then open `/api/health` and press **Run diagnostics** in the dashboard.
5. Keep `HYDRADB_BOLT`, `HYDRADB_TOKEN`, `GRAPHSHIELD_LLM_*` on the backend host only. Never expose Bolt (7687).

```powershell
vercel login
vercel --yes
vercel env add GRAPHSHIELD_BACKEND_URL production
# Optional for disposable demos only: configure GRAPHSHIELD_ADMIN_TOKEN and GRAPHSHIELD_ENABLE_DEMO_RESET=true
vercel --prod
```

## Gateway allowlist
GET `/api/health`, `/api/diagnostics`, `/api/experiments/learning`, `/api/benchmarks/dataflow`; POST `/api/demo/reset`; GET/POST `/api/refund-desk/*`. Everything else returns 404/405. The backend must still enforce its own rate limits, read-only sandbox tools, and approval-only refund actions.

## Cold-start checklist
- [ ] `/api/health` shows `hydradb_connected: true`
- [ ] Diagnostics: all shapes pass
- [ ] Cases load; Investigate streams 5+ MCP events
- [ ] Simulate outage reroutes, Restore recovers
- [ ] Learning and Benchmarks load saved results (no fake data)
- [ ] Demo reset is disabled (403) by default; only enable for an isolated sandbox. Once enabled, backend must verify admin token and rate limit
