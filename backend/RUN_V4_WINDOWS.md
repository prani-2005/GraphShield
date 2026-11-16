# GraphShield V4 — Windows / WSL run guide

This extends your V3 project and preserves the self-hosted open-source HydraDB engine. It does **not** load synthetic demo records for the new evaluation.

## 1. Start the existing HydraDB server in WSL

If it is already running, **do not restart or reseed unnecessarily**. The previously built binary is `/home/pranisha/hydradb/target/debug/graph-node`.

In an Ubuntu terminal (when starting a fresh WSL session):

```bash
cd ~/hydradb
mkdir -p .hydradb/store .hydradb/cache
printf '%s\n' 'local-development-token-32-bytes' > .hydradb/auth-token
export CLOUD_PROVIDER=local
export LOCAL_PATH="$PWD/.hydradb/store"
export GRAPH_NAMESPACE=default
export GRAPH_ID=default
export GRAPH_CELL_ID=cell-0
export GRAPH_CELLS=cell-0
export GRAPH_NODE_ID=node-0
export GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687
export GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687
export GRAPH_DATA_CACHE_DIR="$PWD/.hydradb/cache"
export GRAPH_AUTH_TOKEN_FILE="$PWD/.hydradb/auth-token"
export GRAPH_ALLOW_PLAINTEXT=true
export RUST_MIN_STACK=33554432
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
./target/debug/graph-node
```

Keep the Ubuntu terminal running. The fixed token and plaintext settings are for **localhost development only**.

## 2. Extract the V4 ZIP without overwriting V3

In PowerShell (download the ZIP to Downloads first):

```powershell
cd "$env:USERPROFILE\Downloads"
Expand-Archive -LiteralPath ".\GraphShield_Spec_Implementation_V4.zip" -DestinationPath ".\GraphShield_Spec_Implementation_V4" -Force
cd ".\GraphShield_Spec_Implementation_V4\GraphShield_Hackathon"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 3. Provide real financial XHTML/iXBRL reports (optional but recommended)

The built-in `financial_reporting` MCP adapter is read-only. It works only on files you actually place in an authorized directory:

```powershell
New-Item -ItemType Directory -Force "C:\Users\Public\Documents\GraphShieldReports" | Out-Null
$env:REPORTING_DOCUMENTS_DIR="C:\Users\Public\Documents\GraphShieldReports"
```

Copy your real XHTML/iXBRL reports there. No report samples are fabricated by this repository. Avoid uploading confidential reports to a public demo.

## 4. Add other real tool definitions (optional)

If licensed public OpenAPI files are available, copy real `.json`, `.yaml` or `.yml` specifications into `openapi_sources`. View source metadata first:

```powershell
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli inspect-openapi
```

OpenAPI operations are **converted to tool-schema records for context discovery**. They are not executable MCP connections, and their schema-derived links are flagged as unreviewed.

## 5. Discover, seed and benchmark real tools

```powershell
$env:GRAPH_BACKEND="hydradb"
$env:HYDRADB_BOLT="bolt://127.0.0.1:7687"
$env:HYDRADB_TOKEN="local-development-token-32-bytes"
$env:HYDRADB_GRAPH="default"
$env:REPORTING_DOCUMENTS_DIR="C:\Users\Public\Documents\GraphShieldReports"

.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli stats
.\.venv\Scripts\python.exe -m graphshield.real_mcp tasks
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli diagnostics
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
```

**Note:** `seed` is intended for initial setup. Do not rerun it between an injected failure and your persistence/restart demonstration; repeated MERGE behavior needs validation against your installed HydraDB version.

If discovery skips a server, check the printed error. It never creates pretend tool records to compensate.

## 6. Start the Control Center on port 8801

```powershell
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8801
```

Open `http://127.0.0.1:8801/` in your browser. Keep the terminal running. Use a second PowerShell terminal for CLI benchmarks.

### What to click

1. **Agent workspace:** choose `financial_report_review` if discovered, or another available workflow. Click **Resolve task**. For financial workflows, enter a real report filename such as the exact XHTML file you copied to the permitted folder, then click **Run allowlisted read-only steps** to stream the actual read-only MCP results. Inspect required schemas, rejected tools, and the token estimate. Compare GraphShield with preload-all/lexical. Embedding mode requires optional `sentence-transformers`.
2. **Capability graph:** display the selected dependency path; run **Verify query shapes** and inspect inferred dataflow candidates.
3. **Provider resilience:** choose a task with an actual standby implementation, simulate a primary outage, resolve as Session B, restart FastAPI (not HydraDB), and resolve again. Record both provider names.
4. **Adaptive routing:** run the controlled failure-memory experiment; explain that it is a simulated outage, not autonomous learning from real MCP execution. Optional human-reviewed four-system evaluation requires the dataset described in `REVIEWED_EVALUATION.md`.
5. **Evidence & business:** run the real HydraDB load test and graph-vs-flat lexical ablation. Inspect raw counts and limitations.

### Measure actual LLM token usage (optional provider key)

```powershell
$env:GRAPHSHIELD_LLM_API_KEY="YOUR_PROVIDER_API_KEY"
$env:GRAPHSHIELD_LLM_MODEL="YOUR_SUPPORTED_MODEL_ID"
$env:GRAPHSHIELD_LLM_BASE_URL="https://api.groq.com/openai/v1"
```

Restart FastAPI after setting the variables and click **Run LLM comparison**. This makes an actual provider request and reads its `usage` fields. It does not execute tools. Do not put the API key into the HTML page or GitHub repo.

For an independently reviewed 20–30-task provider benchmark, create `data/evaluation_tasks.json` first, then run:

```powershell
.\.venv\Scripts\python.exe -m graphshield.measured_agent_benchmark --execute-costly --limit 20
```

This makes billable requests. No measured token numbers are invented if the provider or dataset is missing.

### Optional embedding mode

```powershell
.\.venv\Scripts\python.exe -m pip install sentence-transformers
```

The package is intentionally optional. Without it, the embedding baseline returns a clear error instead of silently using lexical search.

### Schema-edge precision review

```powershell
.\.venv\Scripts\python.exe -m graphshield.review_edges export
```

Open `results\edge_review_sample.csv` in Excel. Set `accepted` to `yes` or `no` for each reviewed edge. Then:

```powershell
.\.venv\Scripts\python.exe -m graphshield.review_edges summary
```

If the review is incomplete, the tool reports an incomplete status and does not claim fully sampled precision.

## 7. Public hosting limitation

A Vercel-hosted frontend alone does not host your continuously running Rust HydraDB server. For the live hackathon link, run the open-source `graph-node` and FastAPI on a persistent private Linux host/container, and optionally place a frontend on Vercel. Use TLS, a private Bolt network, proper secrets, a rate limiter/API gateway, and an admin token for dangerous demo endpoints.

`Dockerfile.api` packages the Python API only; it **does not** pretend to deploy or manage HydraDB. The API container needs `GRAPHSHIELD_MCP_CONFIG=/app/mcp_servers_linux.json` and a reachable private HydraDB Bolt server.
