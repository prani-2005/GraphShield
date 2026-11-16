# Gold-task evaluation (source-grounded, no invented records)

The PDF requires 100 manually checked tasks (60 training and 40 held out), a 5-iteration learning study and at least three independent seeds. **This repository does not manufacture those gold labels.** Supply `data/evaluation_tasks.json` with actual reviewed task text and its expected tool **instance** keys. `data/mcp_registry.json` lists the discovered keys.

Each item follows this structure (field names only; replace placeholder values with verified records):

```json
[
  {
    "id": "reviewed-task-001",
    "prompt": "<actual reviewed task description>",
    "task_key": "<existing workflow key>",
    "gold_tool_keys": ["<actual discovered MCP tool key>"],
    "split": "train",
    "review_status": "human_verified",
    "reviewer": "<reviewer or team>",
    "source": "<evaluation source>"
  }
]
```

Do not paste this example verbatim. It is a schema illustration, not benchmark data. The evaluation refuses unverified rows, unknown tools, and missing train/heldout splits.

To run the evaluation (after the real registry is seeded):

```powershell
.\.venv\Scripts\python.exe -m graphshield.reviewed_evaluation_cli
```

A real embedding baseline requires `sentence-transformers`. Without it the embedding arm is reported missing; it is **never** substituted with lexical retrieval.

Learning updates actual HydraDB provider reward properties from verified training labels. It evaluates on separate held-out task prompts and restores original reward values afterward. Rewards from gold labels are supervised routing updates, not autonomous tool-execution outcomes. Report a flat or negative curve honestly if observed.
