---
name: usage-dashboard
description: Token/cost dashboard from ZCode rollout logs (per day, per session, per model, with optional user-supplied pricing)
allowed-tools: Read, Bash, Write
argument-hint: [optional --days N | --prices <file> | --html <file>]
---

Invoke the `usage-dashboard` skill with this input: **$ARGUMENTS**

Run `python3 scripts/usage_report.py` with the arguments the user gave
(`--days`, `--prices`, `--html` pass through directly). Show the markdown
report in the reply. If the user did not supply a price file and asked about
cost, ask for one (JSON of per-model USD per 1M tokens) instead of guessing
prices. If no rollout files are found (exit 1), say where the script looked
and that logs live in `~/.zcode/cli/rollout/`.
