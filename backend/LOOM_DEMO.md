# Three-minute Loom walkthrough — evidence-first

This outline deliberately has no fabricated performance numbers. Use values actually returned from your own V4 results.

**0:00–0:25 — Problem and buyer.** "Enterprise agents connect many MCP services. Loading all tool definitions consumes context, and flat similarity search doesn't guarantee transitive dependencies. GraphShield is an agent-context layer on the self-hosted open-source HydraDB graph-node."

**0:25–1:05 — Context and graph.** In **Agent workspace**, resolve `financial_report_review` if the financial MCP adapter has been discovered, or another verified real workflow. Enter the actual report filename into the authorized-file field, run the financial tools read-only, and show the returned extraction evidence. Compare full registry size with selected schema size, clearly saying *estimated tokens* until measured model results exist. In **Capability graph**, show dependency path and actual query count. Show `real MCP` and `converted OpenAPI` provenance counts.

**1:05–1:45 — Resilience.** In **Provider resilience**, choose an actual task with a primary and standby. Simulate a primary outage, resolve as Session B and show the chosen provider. Restart FastAPI (not HydraDB) and verify the route still avoids the provider. Explain the outage is injected, not real production downtime.

**1:45–2:25 — Evaluation.** In **Adaptive routing**, run the controlled failure-memory test. If you have 60/40 human-reviewed tasks, show the separate four-system held-out report with five iterations and three seeds; otherwise do **not** claim that study exists. In **Evidence & business**, show real load measurements and the flat-lexical ablation and disclose curated gold labels.

**2:25–3:00 — Commercial case.** Explain buyer, usage-based pricing hypothesis, operator governance and limitations. Show the publicly accessible live link and open-source repo. Mention the LAGraph/GraphBLAS native build lessons as source-quality HydraDB feedback.

Before recording, verify that `GRAPH_BACKEND=hydradb`, the source registry was freshly discovered, no mock fallback was enabled, and the metrics in the browser match the JSON saved under `results/`. No source data or passwords should be visible on screen.
