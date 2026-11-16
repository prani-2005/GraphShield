# GraphShield Track 2: REAL MCP edition (Windows + WSL)

## What is real, and what is not

- Tool definitions are obtained **live via the MCP `tools/list` protocol**, not made up or read from a generated fixture.
- HydraDB stores the tool nodes, serialized full input schemas, server nodes, tool-version health, task nodes, skill nodes and directed dependencies. `resolve` performs **actual HydraDB Cypher traversals**.
- Benchmark workflows are **manually authored** for official MCP reference tools and automatically skipped when their real tools are unavailable. They are **not a public independent ground-truth dataset**.
- Tool failures are **simulated injections**; the unhealthy status and `FAILED_ON` relationship are persisted in HydraDB. A separate API process sees the same health state.
- No real remote tool is invoked when resolving. The reference MCP servers are started only to list available schemas.
- JSON length/4 is a **rough token estimate**, not LLM API token usage. Lexical baseline is not embedding retrieval.
- This is an **honest Track 2 prototype**, not proof of production hardening or end-to-end AI agent success.

## Step 1: Start HydraDB (Ubuntu)

Continue to use your already working `~/hydradb/target/debug/graph-node` server on Bolt 7687. Do not interrupt it.

## Step 2: Upgrade GraphShield (Windows PowerShell)

Unzip this ZIP into your Downloads directory, replacing the previous GraphShield_Hackathon project folder **after making a backup**. The new package is a full standalone project.

```powershell
cd "$env:USERPROFILE\Downloads\GraphShield_Hackathon"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
node --version
npm.cmd --version
```

If your `.venv` is absent, run `py -3.12 -m venv .venv` first.

## Step 3: Discover real tools from official MCP servers

The `mcp_servers.json` file contains pinned npm MCP reference servers: two filesystem instances, memory, and sequential thinking. Edit the allowed filesystem path before discovery if `C:\Users\Public\Documents` does not exist on your machine. This is a **read-only discovery operation** from GraphShield's perspective; it doesn't execute any of the reported tools.

```powershell
cd "$env:USERPROFILE\Downloads\GraphShield_Hackathon"
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
```

Discovery produces `data/mcp_registry.json` and `data/real_workflows.json`. Failed servers are recorded explicitly under `errors`. Check the actual tool count; do not claim 160 real tools unless discovery reported 160.

The original source repository is https://github.com/modelcontextprotocol/servers at commit `e1dc4b18dbb948921da37f3d4224a628730b43b0`, supplied by the user. npm packages are separately version pinned; their published package contents may differ from that exact repository commit. The recorded source hash is provenance only, not proof of a matching package build.

## Step 4: Seed into YOUR REAL HydraDB

```powershell
$env:GRAPH_BACKEND='hydradb'
$env:HYDRADB_BOLT='bolt://127.0.0.1:7687'
$env:HYDRADB_TOKEN='local-development-token-32-bytes'
$env:HYDRADB_GRAPH='default'
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.real_mcp tasks
```

The new graph's numeric IDs are deterministically hashed into a separate range, rather than overwriting the old 160 synthetic records. Only use on your local disposable hackathon database.

## Step 5: Real benchmark with corrected request-scoped query counting

```powershell
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 5 --output results\real_mcp_load_5.json
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 10 --output results\real_mcp_load_10.json
```

**Do not claim round-trip reduction against all-tool preload from the graph query count:** preload-all may use zero database queries but a much larger context. The query count measures routing database requests, not LLM tool calls. Only report what the benchmark measures.

## Step 6: Run the browser demo

```powershell
$env:GRAPH_BACKEND='hydradb'
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8798
```

Open http://127.0.0.1:8798/ . Select a task, show the actual chain, inject a failure on **filesystem_primary** using the Fail button, and verify the route switches to **filesystem_standby** when present.

### Prove restart persistence

1. In the dashboard choose `read_document` (if present) and resolve.
2. Fail the tool served by `filesystem_primary`.
3. Verify the selected server becomes `filesystem_standby`.
4. Stop FastAPI with Ctrl+C. **Do not stop HydraDB**.
5. Restart FastAPI and resolve the same task. The standby server must remain selected.
6. Restore health with `POST /real/restore/{tool_id}` to repeat the demonstration later.

Note: The fallback is a second live-discovered **instance of the same real MCP reference filesystem tool**, not an invented tool. Failing it is only an **injected health event**, not actual package crash detection. This matters when explaining the demo to judges.

## What remains for production / final judging

The project does not yet implement an actual LLM request loop, model-billed token comparison, independent public task labels, true automatic schema-derived dependency induction, permission checks on real tool execution, or verified performance at production load. Do not promise those capabilities in the demo.

## Optional real Git + Time MCP tools

The official reference server repository also has Python Git and Time tools. You can extend `mcp_servers.json` with available `uvx` commands and run discovery again. Only supported workflows with the exact named tools appear in the benchmark. Run `uvx --help` to confirm it is installed.
