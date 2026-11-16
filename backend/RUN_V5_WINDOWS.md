# GraphShield V5 — Windows run guide

V5 is a **PDF-aligned Control Center UI** on top of the V4 real-MCP/HydraDB backend. It is not a claim that the PDF's entire evaluation and deployment checklist is complete.

## 1. Set up

Extract `GraphShield_PDF_Aligned_ControlCenter_V5.zip` in Downloads. Open PowerShell:

```powershell
cd "$env:USERPROFILE\Downloads\GraphShield_PDF_Aligned_ControlCenter_V5\GraphShield_Hackathon"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 2. Start HydraDB

Keep your already compiled open-source HydraDB `graph-node` running in WSL using the configuration verified for V2/V3. Do not reset the graph store. In a separate PowerShell terminal, confirm:

```powershell
Test-NetConnection 127.0.0.1 -Port 7687
```

If `TcpTestSucceeded` is false, **start graph-node before proceeding**.

## 3. Configure the API environment

```powershell
$env:GRAPH_BACKEND="hydradb"
$env:HYDRADB_BOLT="bolt://127.0.0.1:7687"
$env:HYDRADB_TOKEN="local-development-token-32-bytes"
$env:HYDRADB_GRAPH="default"
```

Use the real token in your `.hydradb/auth-token` if you changed it. The token printed here is for local development only.

## 4. Reuse already discovered MCP records, or discover them

V5 ships without fabricated snapshots. If you have a working V3/V4 `data/mcp_registry.json`, `data/real_workflows.json`, and `results/real_mcp_benchmark.json`, copy those into the corresponding V5 locations. Otherwise run:

```powershell
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli stats
```

The optional `financial_reporting` MCP adapter may report an error if its local files or prerequisites are unavailable; that should be recorded, not silently replaced with fake tools.

**Important:** An earlier V4 seeding run reported a HydraDB internal error on a repeated `MERGE`. This package includes the idempotency-oriented seed hotfix, but it has not been verified on your live instance. Preserve your data store, run diagnostics first, and only run `seed` if necessary. If it fails, capture the precise error; do not delete existing graph data.

```powershell
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli diagnostics
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
```

## 5. Start the browser dashboard

```powershell
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8802
```

Open http://127.0.0.1:8802 and press Ctrl+F5 once if your browser shows the earlier UI.

## 6. Five screens (matching pages 3–4 of the build spec)

1. **Agent Playground:** enter task text or choose a verified recipe; compare Preload / Embedding / GraphShield; inspect selected tools, estimated context, plan and execution event log. Embedding mode requires `sentence-transformers` installed. GraphShield mode requires a live HydraDB.
2. **Continual Learning:** run the controlled failure experiment and compare static vs adaptive retries. The separate reviewed evaluation panel remains unavailable until reviewed held-out tasks are supplied.
3. **Benchmark & Load:** show saved reports, run graph-vs-flat lexical ablation, and repeat 1/5/10/20-worker routing loads. These measure routing, not full LLM tasks.
4. **Graph Explorer:** examine actual returned edges and the chosen tool chain, query shape diagnostics, and the real tool registry. Schema-derived edges are candidates until reviewed.
5. **Product & Business:** buyers, pricing hypothesis, architecture, provenance, and known limits.

## 7. Notes before Loom

- V5 does not claim 1,000 actual tools, 100 verified tasks, 4-system held-out curves, or a public deployment.
- Never call character/4 estimates provider-measured tokens.
- The failure lab injects a failure; it does not simulate a production MCP failure transparently.
- Only explicitly allowlisted read-only MCP execution is possible; unsupported steps are shown as skipped.
- The graph viewport visualizes the ordered selected route and **separately displays the underlying returned relationship records**. The selected path alone is not an exhaustive graph visualization.
- Public deployment needs a persistent HydraDB host; the Vercel frontend can be public, but Bolt must remain private.
