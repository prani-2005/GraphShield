# V7 Technical Implementation and Evidence Boundaries

## Flagship scenario

“My order arrived nine days late. I want a refund.” We retrieve actual order information from the Olist historical dataset (2016–2018) and apply a transparently **invented** delay policy. Any refund request stays in a local sandbox outbox and requires human approval. No real financial transfer, carrier tracking, or customer message is performed.

## What's implemented

- **Custom MCP registry:** 60 unique tool names in seven domain roles (orders 10, customers 6, payments 8, logistics 8, policy 7, actions 6, catalog/sellers/reviews 15). Orders and payments each have primary/replica/cache **simulated** provider instances. Reference MCP servers remain available. Tool schemas are obtained by the real MCP `tools/list` protocol at discovery time.
- **Source evidence:** Reads the original Olist orders, customers, items, payments, products, sellers and reviews CSVs. The downloader writes a SHA256 provenance manifest and does not create fake customer/order rows.
- **Policy:** `config/demo_refund_policy.json`. 7–13 calendar days after Olist estimated delivery: simulated shipping fee category; 14+ days: simulated order payment category. These are demonstration rules, *not* Olist's refund policy or a verified consumer entitlement.
- **Case generation:** `scripts/build_refund_cases.py` produces 150 cases with actual historical order IDs, generated intents and curated gold tool chains, deterministic seed 17, split 100 training and 50 held-out. Claims are not from real support tickets.
- **HydraDB:** The V6 `RealHydra` Bolt adapter and bounded `Task→Skill→Tool` paths are reused. The new workflow recipes include a seven-step late-order investigation and two-step follow-up. Provider health and routing feedback are stored on actual ToolVersion nodes, with a typed failure relation.
- **Refund Desk UI:** Source-backed order picker; live SSE event timeline; selected graph path and rejected alternatives; cached order context; follow-up; injected failover; restored provider; optional real LLM mode and a controlled experiment summary.
- **Real read-only MCP execution:** The trace calls the selected MCP processes via the SDK, only on the chosen historical order ID. The action-writing tool is not in the public read-only executor.
- **Optional LLM:** An OpenAI-compatible function-calling loop with exactly three meta-tools (`graph_context`, `call_tool`, `report_outcome`). It records provider-reported usage when the configured model returns it; it never substitutes token estimates for measured usage. Reported success is checked against actual tool execution status before updating weights.
- **Controlled evaluation:** Five iterations, three seeds, 100 training/50 held-out order-linked cases. It evaluates route changes and source-linked gold chains against deterministic injected fault probabilities, and writes learning rewards to HydraDB. **This is not equivalent to live tool failure learning, nor to a real LLM end-to-end evaluation.** The preload-all baseline uses an oracle plan, not a model.

## Crucial remaining gaps before claiming full hackathon compliance

- Live V7 tests on the user's Windows/WSL environment (cannot run HydraDB and the Node MCP servers in this artifact environment).
- Human review of task gold chains, especially the "wrong item" hypothetical intent (the Olist CSVs do not prove a wrong item was shipped).
- A controlled real LLM benchmark with the same prompts/cases across modes and provider-reported token usage.
- Review of inferred `PRODUCES`/`CONSUMES` edges: the current V6 inference treats matches as *unreviewed candidates*; its curated `DEPENDS_ON` graph is the verified route source.
- Production-safe public deployment and submission artifacts (HTTPS, authentication, API isolation, GitHub, Loom and posts).

## Why HydraDB is required

Bounded queries resolve the dependency chain through `REQUIRES`, `DEPENDS_ON`, and `IMPLEMENTED_BY`. Selecting an alternative provider relies on shared persisted version-health state. Resolved entity information is persisted through `Entity→RESOLVED_AS→Resolution`. None of those facts are inferred from the local CSV at routing time; the CSV supplies evidence to the invoked tools, while HydraDB supplies their selection and dependency plan.

## V8 addition: online learning under drift (`graphshield/refund_online.py`)

The V7 five-iteration study switches provider once (after iteration 1) and then stays flat, and its preload-all system is an oracle.
V8 adds the experiment judges asked for: a real baseline and repeated adaptation.

- **Stream:** 150 cases, one at a time. Provider reliability for `resolve_order` (primary / replica / cache) is SIMULATED and changes at cases 51 and 101.
- **Systems:** static primary-first, static tuned-at-launch (replica first, never updated), GraphShield learned. Same retry budget (3 providers) for all.
- **Learning:** EWMA success score on `ToolVersion.reward` in HydraDB; first choice comes from a real `resolve()` traversal; the least-recently-tried provider is probed every 10th case; failed probes are counted.
- **Evaluation:** prequential (route chosen before the outcome, learned after), 3 seeds, paired random draws across systems.
- **Control:** `--scenario stationary` (no drift). A hand-tuned static config wins there; the gap is the exploration cost. Report both.
- **Run:** `python -m graphshield.refund_online` (HydraDB) and `python -m graphshield.refund_online --scenario stationary`.
  `--backend memory` is a dry run, written to a differently named file and flagged non-citable.
- **Not claimed:** production outages, LLM success, token savings, or learning beyond provider choice for one capability.
- **Dashboard:** "Adapting when providers change" panel; `GET /api/refund-desk/online-learning`.

Deployment files (`docker-compose.yml`, `Dockerfile.hydradb`, `DEPLOY.md`) are written but **untested**.
