# GraphShield V7 — Late-Delivery Refund Desk (Windows + WSL)

## Honest scope

- Open-source HydraDB must already be running in WSL; **never** use the mock backend for a competition benchmark.
- MCP tool discovery produces real schemas from **custom running MCP servers**. The historical Olist CSVs are real records; customer intents and gold tool chains are authored test scenarios.
- The policy in `config/demo_refund_policy.json` is **invented**. Carrier statuses, configured provider outages, refund approval processing windows, and outbound actions are **simulated**.
- The three order/payment providers all use the **same local CSV snapshot**. They are simulated fault domains, not separate external vendors.
- You get 60 distinct custom tool names across seven roles, with additional provider instances and optional reference MCP tools. The *actual* count must come from `tools/list` output, not this document.
- The default trace is a deterministic, dependency-driven planner plus actual read-only MCP calls. A real LLM loop is available with credentials. No estimated context values are presented as actual model usage.
- **Public safety:** This demonstration must not be exposed directly without proper authentication, HTTPS, rate limiting and a sandbox; a public URL cannot safely expose arbitrary MCP writes or the local HydraDB Bolt port.

## 1. Keep the original HydraDB running in WSL

Open an Ubuntu terminal; if the server is not running, use the same verified startup configuration from your earlier version. Do not delete the `.hydradb/store` directory. You can check reachability from PowerShell:

```powershell
Test-NetConnection 127.0.0.1 -Port 7687
```

`TcpTestSucceeded` must be `True`.

## 2. Download/extract V7 and install dependencies

```powershell
cd "$env:USERPROFILE\Downloads"
Expand-Archive -LiteralPath ".\GraphShield_Refund_Desk_V7.zip" -DestinationPath ".\GraphShield_Refund_Desk_V7" -Force
cd ".\GraphShield_Refund_Desk_V7\GraphShield_Hackathon"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Do not put the ZIP on top of V6.

## 3. Get actual historical source records

```powershell
.\.venv\Scripts\python.exe scripts\fetch_olist.py
.\.venv\Scripts\python.exe scripts\build_refund_cases.py
```

The source mirror and row counts/hashes are recorded in `data/olist/source_manifest.json`. Seven CSVs are required, downloaded from a GitHub mirror of the Olist dataset. If mirror download fails, download the Olist CSVs from the canonical Kaggle dataset and place them under `data/olist`. Never commit or redistribute the source CSVs without reviewing the dataset license.

## 4. Discover live MCP tool definitions and seed HydraDB

```powershell
$env:GRAPH_BACKEND="hydradb"
$env:HYDRADB_BOLT="bolt://127.0.0.1:7687"
$env:HYDRADB_TOKEN="local-development-token-32-bytes"
$env:HYDRADB_GRAPH="default"

.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli stats
.\.venv\Scripts\python.exe -m graphshield.real_mcp tasks
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli diagnostics
```

**Check the discovery errors before seeding.** You need `orders_primary`, `orders_replica`, `orders_cache`, `payments_primary`, `payments_replica`, `payments_cache`, `customers_primary`, `logistics_primary`, `policy_primary`, `actions_primary`, and `catalog_primary`. If a server is skipped, verify that the command uses the virtual environment interpreter and that `data/olist` contains the CSVs.

If `seed` reports an internal HydraDB error, preserve the graph; note the edge/tool in the error. Do not delete the existing database. A fresh *separate* graph is preferable for an isolated benchmark.

## 5. Start the browser

```powershell
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8804
```

Open <http://127.0.0.1:8804/>. The first tab is **Late-Delivery Refund Desk**.

## 6. Three-act demonstration through the UI

1. Click **Reload cases**, select a historical delayed order (prefer the nine-day case), and click **Investigate this order**. Inspect the events, selected dependency chain and rejected providers. Tool results are returned by actual read-only MCP calls.
2. Click **Ask follow-up** for the same order. When the prior investigation successfully cached its order context in HydraDB, the follow-up resolves the two-step path (`get_order_items`, `get_refund_processing_eta`) without an order-resolution MCP call. Compare exact tool counts, not merely elapsed time.
3. Click **Simulate primary outage**. A version-health edge is updated in HydraDB and the case is resolved again. Verify that the `orders_replica` provider replaces `orders_primary` for `resolve_order`. Restart FastAPI without restarting HydraDB or reseeding; repeat the case. Click **Restore primary** after the demo.

The provider outage is *injected*; no actual independent order service is killed.

## 7. Five-iteration / three-seed controlled study

```powershell
.\.venv\Scripts\python.exe -m graphshield.refund_experiment
```

Then click **Load 5-iteration study** in the Refund Desk. The experiment uses 100 training and 50 held-out order-linked cases, but injected provider faults (not real production failures). The preload-all reference uses an **oracle gold plan**, and lexical top-k is a word-overlap baseline. These are not a 4-system real LLM performance evaluation. The original provider reward values are restored after the run.

## 8. Optional real LLM agent and actual token usage

The agent uses exactly `graph_context`, `call_tool`, and `report_outcome` as its LLM-visible meta-tools.

```powershell
$env:GRAPHSHIELD_LLM_API_KEY="YOUR_KEY"
$env:GRAPHSHIELD_LLM_BASE_URL="https://api.groq.com/openai/v1"
$env:GRAPHSHIELD_LLM_MODEL="YOUR_SUPPORTED_FUNCTION_CALLING_MODEL"
```

Use **Run real model** on the Refund Desk in GraphShield and Preload modes. The model must support OpenAI-compatible function calling. Only when an API response includes usage fields will GraphShield report actual token consumption. Compare the same order/question in both modes. The code verifies tool outcome evidence before updating rewards.

Never post tokens, `.env` files, or source datasets to GitHub. A demo LLM run is not automatically a validated customer support resolution.

## 9. Readable failure scenarios

- Data missing: download Olist data first. No fake records are generated.
- MCP `tools/list` failure: check the server-specific error in `data/mcp_registry.json` and Python package installation.
- HydraDB unavailable: check WSL server, Bolt port, auth token; *do not switch to mock mode*.
- Model run unavailable: key/model missing or function-calling API incompatible. The deterministic trace still works but must be labeled as such.
- Failure stored but no fallback: check that replica/cache were discovered and included in the graph, and re-run diagnostics without reseeding.

## 10. Submission boundaries

A public working deployment, a public GitHub repository, a Loom, social posts, actual LLM token comparison over real runs, and independently reviewed generalization claims are not created by this ZIP. Complete and verify these separately before submitting.
