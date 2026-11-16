# GraphShield V9 — Full merged project

This ZIP combines the user-uploaded V8 Python GraphShield project, later refund-only fixes from V8.2, and the **V9 UI + gateway patch**.

## Contents
- `GraphShield_Hackathon/` — Python/FastAPI application, HydraDB/MCP integration, Olist case scripts, refund workflows, controlled experiments, tests, existing Docker/Compose files, and V9 dashboard under `static/`.
- `vercel_frontend/` — separate, complete static dashboard + serverless HTTPS gateway, deployable to your already linked Vercel project.
- `GraphShield_Hackathon/graphshield/v9_evidence.py` — new V9 adapter reading the existing *actual* five-iteration simulated provider-fault report; missing metrics stay null.
- `GraphShield_Hackathon/graphshield/api.py` — routes for diagnostics, learning evidence, candidate dataflow evidence and a deliberately non-mutating reset placeholder.

## Local Windows setup

Keep your HydraDB service running separately on WSL Bolt 127.0.0.1:7687. From PowerShell in `GraphShield_Hackathon`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:GRAPH_BACKEND='hydradb'
$env:HYDRADB_BOLT='bolt://127.0.0.1:7687'
$env:HYDRADB_GRAPH='default'
$env:HYDRADB_TOKEN='local-development-token-32-bytes'
.\.venv\Scripts\python.exe scripts\fetch_olist.py
.\.venv\Scripts\python.exe scripts\build_refund_cases.py
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.refund_experiment
.\.venv\Scripts\python.exe -m graphshield.refund_online --scenario drift
.\.venv\Scripts\python.exe -m graphshield.refund_online --scenario stationary
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8820
```

Open `http://127.0.0.1:8820/`; check `/api/health`, `/api/diagnostics`, `/api/experiments/learning`, `/api/benchmarks/dataflow`. LLM access is optional: the refund investigation mode does not require it. For real model mode, configure `GRAPHSHIELD_LLM_BASE_URL`, `GRAPHSHIELD_LLM_MODEL`, and `GRAPHSHIELD_LLM_API_KEY` *in the same PowerShell session* before starting Uvicorn. Do not put keys inside this ZIP or share them.

## Update existing Vercel frontend

**Deploy only the `vercel_frontend` contents** to the existing linked `GraphShield_Vercel` folder (not the Python directory). Back up the existing directory first.

```powershell
cd "$env:USERPROFILE\Downloads"
Copy-Item -Path '.\GraphShield_V9_Full_Project\vercel_frontend\*' -Destination '.\GraphShield_Vercel' -Recurse -Force
cd '.\GraphShield_Vercel'
vercel --prod
```

The public UI **will not work** until the Vercel environment variable `GRAPHSHIELD_BACKEND_URL` points to an actual public HTTPS FastAPI origin. `http://127.0.0.1:8820` is only a local service and is not reachable from Vercel. Keep Bolt 7687 private, never expose `.env` secrets, and secure public mutation/model endpoints before publishing.

## Evidence and limitations

- New learning endpoint adapts **only** the real saved `results/refund_desk_heldout_injected_faults.json` output from `python -m graphshield.refund_experiment`. This report uses three deterministic seeds, historical order-linked cases, simulated provider outcomes and HydraDB routing. It is not measured LLM performance. Missing model round-trip and latency fields remain `null`.
- New dataflow benchmark reports inferred schema-matching **candidate** links from `results/inferred_edges.json`, not confirmed persisted `PRODUCES`/`CONSUMES` graph relationships. The flat-vs-graph comparison invokes the existing live HydraDB ablation. It does not fabricate plan correctness, dependency graph query counts, manual review, or licensed tool sources. It reports absence when data isn't available.
- `/api/demo/reset` is intentionally `501 Not Implemented`: no safe transactional HydraDB reset exists. The reset button is disabled. No graph state is erased to mimic a reset.
- Existing `docker-compose.yml` and Dockerfiles are preserved from the uploaded V8 code, **not validated for deployment** here. Test them before claiming publicly hosted HydraDB.
- This is not a publicly deployed backend. Vercel backend URL and hosted HydraDB remain to be configured.
- Five obsolete pre-refund workflow/UI test expectations have been retained as `xfail` (explicitly marked, not silently deleted). New V9 evidence tests cover endpoint presence, no-fake-metric fields, missing-result 404, and reset safety.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Local validation during packaging: `42 passed, 5 xfailed` (legacy pre-refund tests), JavaScript syntax checks passed. These tests do not replace live HydraDB or browser integration tests.
