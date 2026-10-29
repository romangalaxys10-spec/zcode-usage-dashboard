---
name: usage-dashboard
description: Build a token and cost dashboard from ZCode rollout logs (~/.zcode/cli/rollout/model-io-sess_*.jsonl). Use when a user asks how many tokens they used, what their ZCode sessions cost, which model they use most, or wants a daily/session/model usage report. Produces a markdown table and an optional HTML report; cost estimation only when a per-model price JSON is provided.
---

# usage-dashboard

Turn ZCode's own model-I/O logs into a usage report: tokens per day, per
session, per model, and estimated cost when you supply prices. Stdlib only,
runs on macOS, Linux, and Windows.

## The log format (what the script parses)

Each file in `~/.zcode/cli/rollout/` named `model-io-sess_*.jsonl` holds one
JSON object per turn, one per line. Fields the script reads (in priority
order, so renamed fields still work):

- timestamp: `timestamp`, `ts`, `time`, `date`, or `createdAt`
- session: `sessionId`, `session_id`, `session`, `turnId`
- model: top-level `model` (may be a string or an object with `modelId`/`id`),
  `modelName`, `model_id`, or `m`
- tokens: a `usage` (or `usageInfo` / `tokens`) object with `inputTokens`,
  `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`,
  `totalTokens` (snake_case and OpenAI-style `promptTokens` /
  `completionTokens` are accepted too)

Known quirk: with some new-api style proxies, `outputTokens` comes back as
`0` even when the model produced output (the proxy omits the completion
count). The script reports how many turns are affected and marks output and
cost figures as lower bounds in that case. It does not invent numbers.

## 1. Generate the markdown report

```bash
python3 scripts/usage_report.py
```

Output: files scanned, total turns, token totals, then three tables
(per day, per session, per model) with input / output / cache / turns
columns. Exit codes: 0 success, 1 no files or no parseable turns, 2 bad
`--prices` file.

Useful flags:
- `--days N`: only count turns from the last N days.
- `--limit N`: cap rows shown per table.
- `--glob <pattern>`: point at a different log directory.
- `--html out.html`: also write a self-contained HTML report.

## 2. Add cost (optional, user-supplied prices)

No prices are hardcoded in the script. To estimate cost, the user provides a
JSON file of per-model prices in USD per 1M tokens:

```json
{
  "agnes-3.0-flash": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
  "gpt-5.1": 2.5
}
```

Per-model objects (input / output / cache_read / cache_write) or a single
number per model are both accepted. Then:

```bash
python3 scripts/usage_report.py --prices prices.json
```

The cost column only fills in for models present in the price file;
unpriced models show `n/a`, and unpriced turns are excluded from the total.
Saying that out loud in the answer is part of being honest about estimates.

## 3. Present the result

Copy the markdown report (or its tables) into the reply. When the
`outputTokens=0` note fires, say so in one sentence so the user knows the
output/cost side is a lower bound. If they want a file, pass `--html` and
name the path.

## Guardrails

- Read-only: the script never writes anything except the optional `--html`
  target the user asked for.
- Logs may contain prompts and tool output. Do not paste log contents into
  chat or other files; use only the aggregate numbers.
- Totals are exact for whatever is on disk; "cost" is always an estimate
  that depends on the prices the user supplied.
