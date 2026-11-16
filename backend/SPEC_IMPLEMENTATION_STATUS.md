# Implementation audit against uploaded 11-page GraphShield build spec

The file *GraphShield: Build Spec for the HydraDB Hackathon* is the requirements baseline. This version is an extension of V3, not a rewrite. **Implementation** means source code is present and locally checked; **verified live** requires the operator to run on Windows against their self-hosted HydraDB and MCP servers.

| Specification area | V4 status | Evidence / remaining work |
|---|---|---|
| Open-source HydraDB | Existing real integration preserved | Prior real-MCP benchmark used live Bolt `graph-node`; rerun V4 locally |
| Task-to-tool bounded traversal | Existing code retained | `real_mcp.RealHydra.resolve`; database diagnostics added |
| 1,000+ real tools | Import pipeline added, count NOT claimed | `enterprise.py` loads genuine licensed OpenAPI files and MCP discovery; 38 were verified in the prior V3 run. Operator must supply enough source specs and rerun discovery |
| MCP tools/list real discovery | Existing, financial MCP added | `real_mcp.discover_server` and `financial_mcp.py`; local tool call required to verify |
| OpenAPI provenance | Implemented, unit tested | Source SHA256, title, version, converted operation metadata |
| Automatic dataflow candidates | Implemented, unit tested | `PRODUCES` / `CONSUMES` edges seeded from normalized name+type; candidate confidence 0.65 in the review report, NOT verified dependencies. Relationship property confidence is not yet live-verified |
| Review of 50 inferred edges | Review tooling implemented | `review_edges.py`; human must annotate CSV, precision not invented |
| Task dependency / provider health | Existing graph routing retained | Current 9 V3 curated workflows, plus financial workflows if discovered; provider reward feedback added, live correctness still needs verification |
| 100 verified task labels (60/40) | Data contract + evaluator implemented | No 100 gold records were invented. User must provide human-verified `data/evaluation_tasks.json` |
| Four arms, five iterations, three seeds | Evaluation harness implemented | `reviewed_evaluation.py`, but cannot produce legitimate learning curve before gold data exists and live verification passes |
| Preload vs lexical vs embedding | All routing modes wired | True embedding requires `sentence-transformers`; no lexical substitution |
| Graph vs flat ablation | Implemented, must evaluate | `enterprise_runtime.flat_ablation`; baseline is explicitly flat lexical without traversal |
| Measured model tokens | Optional live API integration implemented | Actual provider usage fields, only with real API key/model; no billed usage captured here |
| 20–30 held-out measured model requests | CLI implemented | `measured_agent_benchmark.py`; requires 20 held-out verified tasks and explicit billable request acknowledgement |
| MCP execution | Restricted read-only execution only | SSE streams started/skipped/result/error for allowlisted zero-argument tools and filename-restricted read-only financial operations; NOT a full arbitrary multi-step agent executor |
| Entity memory | Existing HydraDB retrieval and upsert | No proven TTL enforcement; do not claim expiry behavior |
| Failure memory | Existing persisted provider status and failure edge | Must verify restart test in V4; failure is injected, not production outage |
| Continual-learning behavior | Feedback updates version reward | Not proven to improve held-out success. Controlled failure-memory experiment remains explicitly simulated |
| Load benchmark | Real repeated-request harness implemented | 1/5/10/20/50 option, actual numbers only from local runtime. No new benchmark measured in this environment |
| UI | Five professional views implemented | `static/index.html` Agent workspace / Capability graph / Provider resilience / Adaptive routing / Evidence & business |
| Public hosting | API Dockerfile supplied | No deployed public link, private database, production API gateway or cloud provisioning has been performed |
| GitHub / Loom / social submission | Instructions only | User must push, record, post, and submit |

## Verified locally in artifact builder

- 17 Python tests passed.
- Python files passed `compileall`.
- Dashboard JavaScript passed Node syntax check.
- FastAPI application imported and registered the new routes.
- A local Chromium visual render was blocked by the tool environment, so final UI appearance and live clicking still need Windows verification.

## Hard limitations you must disclose

1. Existing MCP discovery was verified in V3 using 38 tool entries across four server instances; V4 adds a new real local financial MCP server, but its tool availability has not yet been proven from the operator machine.
2. Source-backed OpenAPI tool metadata is **not** executable via MCP unless a corresponding adapter is configured.
3. Candidate output→input matches are *not* fully approved/true dependency edges until reviewed.
4. Learning from manually labeled routes is supervised routing updates, not online RL or validated performance growth.
5. Full LLM agent, real external provider failures, real billed usage, and public HTTPS deployment require external credentials and services.
6. The dashboard never uses hardcoded benchmark scores; reports display only available saved results or explicit empty/error states.
