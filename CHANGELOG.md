# Changelog

## 0.1.0 - 2026-10-29

- Initial release: parses ZCode rollout JSONL logs (~/.zcode/cli/rollout/model-io-sess_*.jsonl) tolerating missing or renamed fields.
- Aggregates token counts per day, per session, and per model.
- Optional cost estimation from a user-supplied per-model price JSON (no hardcoded prices).
- Markdown table output plus optional self-contained HTML report, stdlib only.
