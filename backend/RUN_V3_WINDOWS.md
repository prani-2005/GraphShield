# GraphShield V3 — Windows PowerShell runbook

This package extends **GraphShield_RealMCP_Track2_v2**. It does NOT ship made-up MCP tool data. It reads your locally discovered registry from `data/mcp_registry.json`. Because this ZIP is a source bundle, discovery and seed run on your computer.

## 1. Leave the HydraDB Rust server running in WSL Ubuntu

Your existing `graph-node` on `bolt://127.0.0.1:7687` must remain active. Do not delete the prior graph or reuse mock mode for the demo.

## 2. New PowerShell window — extract and install

```powershell
cd "$env:USERPROFILE\Downloads"
Expand-Archive -LiteralPath '.\GraphShield_ControlCenter_v3.zip' -DestinationPath '.\GraphShield_ControlCenter_v3' -Force
cd '.\GraphShield_ControlCenter_v3\GraphShield_Hackathon'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 3. Configure HydraDB in the SAME terminal

```powershell
$env:GRAPH_BACKEND="hydradb"
$env:HYDRADB_BOLT="bolt://127.0.0.1:7687"
$env:HYDRADB_TOKEN="local-development-token-32-bytes"
$env:HYDRADB_GRAPH="default"
```

## 4. Discover, seed, benchmark

These commands contact real MCP servers via `tools/list` and seed the actual HydraDB graph. **Don't use `graphshield.benchmark`**, which is the old synthetic benchmark.

```powershell
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
```

Discovery requires `node` and `npm.cmd`. If npm servers are already installed, discovery may still use `npx.cmd` to start them. Importing the registry into a new copy does not erase the old GraphShield project files, but *reseeding can reset tool-version properties in the shared HydraDB graph*. Do not reseed between the failure test and the restart demonstration.

## 5. Start the dashboard

```powershell
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8799
```

Open <http://127.0.0.1:8799/>. If 8799 is already occupied by the V2 app, close the V2 Uvicorn process with Ctrl+C or use port 8800 and open that port instead.

## 6. Loom walkthrough entirely in browser

1. **Agent playground**: select `edit_document`, click Resolve; see real tool schemas and the per-task estimate; select Graph explorer to view the live-resolved path and edge evidence.
2. **Failure lab**: click Load edit-document workflow, then Simulate Agent A failure, then Agent B: resolve again. Confirm primary becomes standby. *Restart the dashboard process without reseeding* to demonstrate persistence; reload and resolve again. Click Restore primary when finished.
3. **Learning lab**: select `edit_document` and run 8 iterations. The chart is generated from real HydraDB graph resolutions and controlled failure injection, with the tool restored automatically afterward. This proves reuse of failure memory, not autonomous ML training.
4. **Benchmarks & business**: view the saved real-MCP benchmark, refresh it, and click Run hard-task check. Hard-task score is for manually written paraphrases and transparent lexical matching, not public ground truth.
5. **Agent playground**: optionally execute an allowlisted, zero-parameter read-only MCP tool. The server must be available locally; no arbitrary tool execution is exposed.

## Known limits — disclose to judges

- Real schemas are collected via MCP `tools/list`; the workflows are manually curated.
- `6,329` and `412` were earlier local estimates; the app reads YOUR current benchmark, it does not hardcode those values.
- The learning demo measures failed-dispatch attempts with **injected** outages and a static baseline; it is not actual downstream API failure learning or training an ML model.
- The browser's free-text entry uses an interpretable lexical selector; it is not a full LLM planner.
- A restricted read-only MCP call is possible, but the general workflow router still resolves rather than automatically executing the chain.
- A single local HydraDB node behind localhost is not a public deployment. For a public Vercel frontend, host the API and self-hosted open-source HydraDB on persistent Linux infrastructure.
