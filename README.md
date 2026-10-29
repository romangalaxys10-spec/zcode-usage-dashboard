# Usage Dashboard

A token and cost dashboard built from ZCode's own rollout logs.

## Why

You cannot tune your model choices or explain your bill when usage is a black box. ZCode writes every model turn to JSONL under `~/.zcode/cli/rollout/`, but nobody has an answer for "how many tokens did I use this week, on which model, at what cost". This plugin turns those logs into a readable report without leaving your machine.

## How it works

1. Reads every `model-io-sess_*.jsonl` in the rollout directory (one JSON object per turn).
2. Extracts timestamp, session id, model, and input/output/cache token counts, tolerating missing or renamed fields.
3. Aggregates per day, per session, and per model.
4. Estimates cost only if you pass a per-model price JSON (`--prices`); no prices are hardcoded anywhere.
5. Emits a markdown table to stdout and, with `--html`, a self-contained HTML file.

## Install

Option A: self-installable marketplace. Download or clone this repo, open ZCode, go to Plugin Marketplace, Add, Add Plugin Marketplace, paste the folder path, then Install `usage-dashboard`.

Option B: manual copy. Copy the `usage-dashboard` folder into your ZCode workspace `plugins/` directory and reload plugins.

## Try it

```
/usage-dashboard --days 7
```

Expected result: total turns and tokens for the last seven days, then three tables (per day, per session, per model) with input / output / cache / turns columns. To add a cost column, create a small price file:

```json
{ "agnes-3.0-flash": { "input": 1.0, "output": 5.0, "cache_read": 0.1 } }
```

USD per 1M tokens, then run `/usage-dashboard --days 7 --prices prices.json`.

## Requirements

Python 3.8+, stdlib only. Access to your `~/.zcode/cli/rollout/` directory. Costs are estimates based on your price file; with new-api style proxies, `outputTokens` can report 0 even when the model produced output, so output and cost figures are lower bounds in that case. The report prints a note when it detects this.

---

<p align="center">
  <a href="https://z.ai/subscribe?ic=R0K78RJKNW"><img alt="z.ai coding plans - 10% OFF coupon" src="https://img.shields.io/badge/z.ai%20coding%20plans-10%25%20OFF%20coupon-blueviolet" /></a>
  <a href="https://zcode.z.ai/invite/ALWM9JUA"><img alt="Try ZCode free" src="https://img.shields.io/badge/Try%20ZCode-free%20invite-0969da" /></a>
</p>

## License

MIT.
