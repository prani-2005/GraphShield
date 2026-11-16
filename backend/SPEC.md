# GraphShield v0.1 specification

## Goal
Agent calls `resolve(task_key, token_budget)`. Graph traverses Task->Skill,
Skill->Skill dependencies, Skill->Tool and Tool->ToolVersion, selects only
healthy candidate tools, and reuses Entity->Resolution when present.

## Graph schema
- Task -[:REQUIRES]-> Skill
- Skill -[:DEPENDS_ON]-> Skill (prerequisite)
- Skill -[:IMPLEMENTED_BY]-> Tool
- Tool -[:HAS_VERSION]-> ToolVersion {status,version,reward}
- Tool -[:FAILED_ON]-> Failure
- Entity -[:RESOLVED_AS]-> Resolution

The chosen route is prerequisite-first and is returned with alternatives.
Each directed edge is persisted by HydraDB queries; no local sidecar registry
is consulted for selecting tools in live mode. Schema payloads are demo
fixtures indexed by graph-returned tool ID, because large JSON schemas do not
need to be graph properties.

## API
POST /seed — create deterministic graph; reserved ids 10000..69999.
POST /resolve {"task_key":"accounts_000","token_budget":2400}
POST /failure {"tool_id":10000,"error_kind":"unavailable"}
POST /healthy/{tool_id}
POST /success {"tool_ids":[10000,10001]}
POST /entities {"key":"company_0","value":"Demo Corp 0 Ltd","source":"demo"}
POST /execute {"task_key":"accounts_000","inject_failure":10006}
GET /health

`resolve` returns tools, schema, resolved entity, skill path, graph edges,
rejected alternatives with reasons, estimated schema tokens, graph query count.

## Demo acceptance
1. Real HydraDB Graph MATCH on directed edges returns prerequisites.
2. Failed tool version is excluded for all subsequent resolves.
3. Success reward increments routing score, changing tie-breaking when strong.
4. Benchmark runs 48 synthetic tasks against 160 tool definitions.
5. Time, token proxy, graph calls and routing recall are separately disclosed.

## Deliberate limitations
- No actual LLM or paid provider is required; demo executor is a deterministic stub.
- Learning is edge-associated tool-version reward, not automatic model training,
  not path compression and not evidence of decreasing token usage.
- Version compatibility is not fully modeled yet; unhealthy status reroutes to
  another versioned tool provider for the same skill. True pairwise compatibility
  checking is a next implementation step.
- No concurrency-safe compare-and-swap for rewards; demo reward writes are sequential.
- Only one seeded version per tool, alternatives are separate tool nodes.
- No remote MCP tool execution. See existing official hydradb-mcp for a separately
  deployed MCP memory service; this app uses Bolt for graph traversal directly.
- Schema token metric uses JSON character count / 4, not real model token usage.
- The lexical top-k benchmark is **not** a vector embedding baseline.
- In-memory mode is a test simulator, not proof of HydraDB performance.
- Node numeric IDs are reserved for the hackathon project. Use a separate graph.
