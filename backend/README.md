# GraphShield V7 — Late-Delivery Refund Desk

**Start here:** [RUN_V7_WINDOWS.md](RUN_V7_WINDOWS.md). For implementation details and factual limitations see [REFUND_DESK_IMPLEMENTATION.md](REFUND_DESK_IMPLEMENTATION.md).

# GraphShield Commerce — Track 2

**Flagship scenario: e-commerce delayed-order investigation using real anonymized Olist historical records.** This retains the original generic HydraDB infrastructure but replaces file editing as the first customer-facing demonstration.

See **COMMERCE_DEMO.md** for dataset provenance, commands, capabilities and limitations. Download original CSVs using `py -3.12 scripts\fetch_olist.py`, then run MCP discovery and seed HydraDB. Never use synthetic rows in the demo or claim these historical orders are current.

---

# GraphShield — Open-source HydraDB agent-context layer (V4)

A professional, source-backed Track 2 hackathon implementation extending GraphShield Control Center V3. GraphShield retrieves **task-specific MCP tool schemas** through directed, bounded traversals in the **self-hosted open-source HydraDB engine**, rather than preloading all tool definitions. It records provider failures and selection feedback and exposes provenance, benchmarking and limitations in the browser.

## Quick start on Windows

See **[RUN_V4_WINDOWS.md](RUN_V4_WINDOWS.md)** for step-by-step WSL, Python, real MCP discovery, seeding, benchmarking and browser run commands. It uses port **8801** to avoid your previous V3 server on 8800.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
# Set GRAPH_BACKEND, HYDRADB_BOLT, HYDRADB_TOKEN, HYDRADB_GRAPH
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8801
```

## Architecture

Browser dashboard → FastAPI → real MCP discovery (stdio) and HydraDB over Bolt → persistent `Task`, `Skill`, `Tool`, `ToolVersion`, `MCPServer`, `Entity`, `Resolution`, `Failure`, `DataType` and typed relationship edges.

Bounded graph traversal follows `Task -REQUIRES-> Skill -DEPENDS_ON-> Skill -IMPLEMENTED_BY-> Tool -HAS_VERSION-> ToolVersion`. Provider status and learned rewards influence selection. New source-backed OpenAPI `Tool -PRODUCES-> DataType <-CONSUMES- Tool` links are candidate dataflow evidence, **not trusted execution prerequisites**.

## What's new in V4

- Professional five-screen enterprise dashboard with provenance, comparison modes, graph evidence, failure demo, learning and load charts, diagnostics and business positioning.
- Genuine source-backed OpenAPI import (`openapi_sources/`) alongside the existing MCP `tools/list` discovery. No invented registry records.
- A **Financial Reporting Operations** MCP adapter for actual local XHTML/iXBRL: list reports, inspect metadata, extract financial tables and inline facts, check structural issues and generate a read-only audit summary. This is not formal financial filing validation.
- Per-task query accounting and repeated-request p50/p95/p99/throughput/error benchmark support.
- Optional real embedding retrieval (`sentence-transformers`), explicit word-overlap baseline, and optional model calls returning **provider-reported** usage fields.
- Source-grounded schema candidate edge review and a 5-iteration/3-seed supervised learning evaluation contract requiring separately reviewed train/held-out labels.
- Write controls, basic per-process rate limiting, CORS and a separate API container Dockerfile. Public production deployments still need private database networking, TLS, external API gateway and secrets management.

## Main API

`GET /api/health`, `/api/registry/stats`, `/api/tools`, `/api/diagnostics`, `/api/graph/inference`, `/api/ablation`, `/api/benchmark/results`, `POST /api/resolve`, `/api/failures`, `/api/feedback`, `/api/entities`, `/api/execute` (read-only SSE), `/api/experiments/learning`, `/api/experiments/reviewed`, `/api/benchmark/load`, and `/api/agent/run` (optional measured LLM call).

Earlier V3 `/real/*` and `/demo/*` routes remain for compatibility.

## Real data and reproducibility

- MCP: `mcp_servers.json` pins published reference-server packages. The filesystem primary/standby are two instances of the same package, not independent vendors.
- Financial MCP: uses only operator-supplied files in `REPORTING_DOCUMENTS_DIR`; test inputs are never counted as real benchmarks.
- OpenAPI: reads genuine operator-supplied JSON/YAML specs and stores their SHA256 + version, not a fabricated tool list. Check source licenses.
- Curated workflows: built-in recipes operate only if tool names were genuinely discovered; optional `data/approved_workflows.json` requires explicit `human_verified` records.
- Independent gold tasks: `data/evaluation_tasks.json` is intentionally absent. See **[REVIEWED_EVALUATION.md](REVIEWED_EVALUATION.md)**. No 100-task accuracy or learning result is claimed without it.
- Old V3 verified numbers (38 real entries, 9 curated workflows, 6,329 vs 412 estimated JSON/4 schema tokens) are **historical V3 results**, not new V4 benchmarks. New reports are produced only by your local runs.

## Deployment, security and known gaps

`Dockerfile.api` containerizes the API and Node-based MCP discovery, but the compiled Rust `graph-node` must run as a separate persistent service. A Vercel frontend alone cannot host this database. Restrict Bolt to a private network, set `GRAPHSHIELD_ADMIN_TOKEN`, use HTTPS and an API gateway/rate limiter, never allow anonymous arbitrary file writes. Do not publish local datasets or proprietary reporting documents.

See **[SPEC_IMPLEMENTATION_STATUS.md](SPEC_IMPLEMENTATION_STATUS.md)** for a point-by-point audit against the attached 11-page build spec, including capabilities that remain unverified or incomplete.

## HydraDB feedback

In WSL Ubuntu, the initial Rust build linked against LAGraph but `just native-check` did not detect the missing native library. The developer had to build GraphBLAS 10.5.2 and LAGraph from source. HydraDB's bounded Cypher subset also requires careful query-shape testing. The added diagnostics endpoint reports support on the actual running version.

## Claims not made

No fabricated enterprise data, no fake measured token counts, no invented learning curves or public deployment. The tool-context estimates are JSON character length / 4. The execution endpoint permits a small allowlist of read-only MCP calls, including filename-restricted financial analysis on real local XHTML/iXBRL files; it is not a general autonomous workflow executor.
