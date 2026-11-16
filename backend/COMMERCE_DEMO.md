# GraphShield Commerce — Live Evidence-Based Customer Operations Demo

## Business problem

A customer contacts support about a delivery that arrived after the estimated date. A support agent needs verified order status, customer context, line-item and payment evidence, and delivery-date comparison. A large MCP registry is wasteful; GraphShield resolves only the required tool definitions through the **self-hosted open-source HydraDB engine**.

## Source and limitations

Original **Olist Brazilian E-Commerce Public Dataset**: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

Four exact CSVs are downloaded via `scripts/fetch_olist.py` from a public GitHub mirror. No customer/order records are shipped with this project; no records are generated as fallbacks. Data are anonymized historical orders from approximately 2016–2018 (not live store orders or a live shipping API). Review the dataset's license (commonly reported as CC BY-NC-SA 4.0) before commercial redistribution; the script records provenance and SHA256 for each file. Avoid presenting this dataset as current customer traffic.

## Actual MCP tools

| Tool | Data it reads |
|---|---|
| `find_delayed_orders` | Historically delivered-late orders (for selecting a case) |
| `get_order_status` | Order status and delivery timestamps |
| `get_customer_context` | Anonymized customer ID, region |
| `get_order_items` | Products/sellers and prices |
| `get_order_payments` | Payment types and recorded amounts |
| `assess_delivery_timing` | Whether actual delivery exceeded estimate |

All calls are **read-only** and accept only a validated `order_id` where required. There is no refund eligibility decision, refund issuance, shipping-provider retry, actual LLM planning, or customer notification.

## Windows run

1. Start the existing HydraDB `graph-node` in WSL (Bolt `7687`).
2. From the extracted project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\fetch_olist.py
$env:GRAPH_BACKEND="hydradb"
$env:HYDRADB_BOLT="bolt://127.0.0.1:7687"
$env:HYDRADB_TOKEN="local-development-token-32-bytes"
$env:HYDRADB_GRAPH="default"
.\.venv\Scripts\python.exe -m graphshield.real_mcp discover
.\.venv\Scripts\python.exe -m graphshield.real_mcp seed
.\.venv\Scripts\python.exe -m uvicorn graphshield.api:app --host 127.0.0.1 --port 8803
```

3. Visit `http://127.0.0.1:8803/`. Select **commerce order investigation**, click **Load cases**, select an actual order, **Resolve task**, then **Execute safe plan**. GraphShield uses HydraDB for tool dependency traversal and MCP for real tool calls. The case selector is local CSV inspection solely for choosing a real order.
4. Open **Graph Explorer**, **Benchmark & Load** to inspect query evidence and context size. Run a fresh real-MCP benchmark to update measured routing values.

### Validating the new live registry

```powershell
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli stats
.\.venv\Scripts\python.exe -m graphshield.enterprise_cli diagnostics
.\.venv\Scripts\python.exe -m graphshield.real_mcp benchmark --concurrency 1
```

Check that `commerce_evidence` is in the discovered server list. If its MCP startup fails, inspect stderr and check that the project's `.venv` has `mcp` installed.

## How to pitch

> “A customer contacts support about a delayed delivery. We use five real read-only commerce capabilities, resolve their order through HydraDB's task-to-skill-to-tool graph, and fetch historical customer, order, item, payment and delivery evidence from the original Olist dataset. The agent is not given all MCP tool schemas upfront. The graph also supports provider health and shared failure memory. We report estimated schema-context reductions separately from actual model usage.”

### Unfinished work (do not claim as complete)

Independent enterprise API providers, financial refund policy adjudication, actual LLM-executed multi-tool automation, independently labeled 100-task continual-learning evaluation, production deployment and permissions. The dashboard remains a controlled evidence demo.
