#!/usr/bin/env python3
"""usage_report.py: aggregate token/cost from ZCode rollout logs.

Reads JSONL files matching ~/.zcode/cli/rollout/model-io-sess_*.jsonl
(one object per turn). Per turn it extracts the timestamp, session id,
model, and input/output/cache token counts, tolerating missing or
renamed fields. Aggregates per day, per session, and per model, and
estimates cost only if a per-model price JSON is supplied via --prices.

Stdlib only. Exit codes:
  0  success (report emitted)
  1  no matching log files found, or zero parseable turns
  2  bad --prices file

Example:
  python3 usage_report.py
  python3 usage_report.py --days 7 --html report.html
  python3 usage_report.py --prices my_prices.json
"""

import argparse
import glob
import html
import json
import os
import re
import sys
from collections import defaultdict

DEFAULT_GLOB = os.path.expanduser("~/.zcode/cli/rollout/model-io-sess_*.jsonl")


def pick(d, *names, default=0):
    """Return first present-and-numeric value among key names, else default."""
    for n in names:
        v = d.get(n)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            m = re.fullmatch(r"-?\d+(\.\d+)?", v.strip())
            if m:
                return float(m.group())
    return default


def find_usage(o):
    """Locate a token-usage dict in a turn, tolerating nesting and renames.

    Checked in order: top-level usage/usageInfo/tokens, response.usage,
    response.usageInfo, then any top-level dict value that contains a
    tokens key (covers providerMetadata and other wrappers).
    """
    for key in ("usage", "usageInfo", "tokens"):
        v = o.get(key)
        if isinstance(v, dict):
            return v
    for nest_key in ("response", "request", "result", "data"):
        v = o.get(nest_key)
        if isinstance(v, dict):
            for key in ("usage", "usageInfo", "tokens"):
                inner = v.get(key)
                if isinstance(inner, dict):
                    return inner
    for v in o.values():
        if isinstance(v, dict) and any(k in v for k in (
                "inputTokens", "input_tokens", "outputTokens",
                "output_tokens", "promptTokens")):
            return v
    return {}


def parse_turns(paths):
    """Yield (timestamp_str, session, model, in_tok, out_tok, cache_read, cache_write)."""
    turns = []
    for path in paths:
        try:
            fh = open(path, "r", encoding="utf-8")
        except OSError as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        with fh:
            for i, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(o, dict):
                    continue
                ts = (o.get("timestamp") or o.get("ts") or o.get("time")
                      or o.get("date") or o.get("createdAt")
                      or o.get("startedAt") or o.get("completedAt") or "")
                session = (o.get("sessionId") or o.get("session_id")
                           or o.get("session") or o.get("turnId") or "unknown")
                model = o.get("model") or o.get("modelName") or o.get("model_id")
                if isinstance(model, dict):
                    model = model.get("modelId") or model.get("id")
                if not model:
                    m = o.get("m")
                    if isinstance(m, dict):
                        model = m.get("modelId") or m.get("id")
                    for nest_key in ("request", "response"):
                        v = o.get(nest_key)
                        if isinstance(v, dict):
                            cand = v.get("modelId") or v.get("model")
                            if isinstance(cand, str):
                                model = cand
                            elif isinstance(cand, dict):
                                model = cand.get("modelId") or cand.get("id")
                            if model:
                                break
                model = model or "unknown"
                usage = find_usage(o)
                tin = pick(usage, "inputTokens", "input_tokens", "promptTokens",
                           "prompt_tokens", "input")
                tout = pick(usage, "outputTokens", "output_tokens",
                            "completionTokens", "completion_tokens", "output")
                cr = pick(usage, "cacheReadTokens", "cache_read_tokens", "cacheRead")
                cw = pick(usage, "cacheWriteTokens", "cache_write_tokens", "cacheWrite")
                total = pick(usage, "totalTokens", "total_tokens", "total")
                if total == 0 and (tin or tout or cr or cw):
                    total = tin + tout + cr + cw
                turns.append((str(ts), str(session), str(model),
                               tin, tout, cr, cw, total))
    return turns


def load_prices(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"bad --prices file: {e}", file=sys.stderr)
        sys.exit(2)
    # accept {model: {input, output}} or {model: price_per_million_tokens}
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = {
                "input": float(v.get("input", v.get("input_per_million", 0)) or 0),
                "output": float(v.get("output", v.get("output_per_million", 0)) or 0),
                "cache_read": float(v.get("cache_read",
                                          v.get("cacheRead_per_million", 0)) or 0),
                "cache_write": float(v.get("cache_write",
                                           v.get("cacheWrite_per_million", 0)) or 0),
            }
        else:
            p = float(v)
            out[k] = {"input": p, "output": p, "cache_read": p, "cache_write": p}
    return out


def cost_of(turn, prices):
    """Return cost (or None if model has no price)."""
    ts, session, model, tin, tout, cr, cw, total = turn
    p = prices.get(model)
    if not p:
        return None
    return (tin * p["input"] + tout * p["output"]
            + cr * p["cache_read"] + cw * p["cache_write"]) / 1_000_000.0


def day_of(ts):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", ts or "")
    return m.group(1) if m else "unknown-date"


def aggregate(turns):
    per_day = defaultdict(lambda: [0, 0, 0, 0])
    per_sess = defaultdict(lambda: [0, 0, 0, 0])
    per_model = defaultdict(lambda: [0, 0, 0, 0])
    zero_out = 0
    for ts, session, model, tin, tout, cr, cw, total in turns:
        for bucket, key in ((per_day, day_of(ts)), (per_sess, session),
                            (per_model, model)):
            b = bucket[key]
            b[0] += tin
            b[1] += tout
            b[2] += cr + cw
            b[3] += 1
        if tout == 0:
            zero_out += 1
    return per_day, per_sess, per_model, zero_out


def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))


def md_table(title, rows, columns, prices=None, known_model=False):
    lines = [f"### {title}", "",
             "| " + " | ".join(columns) + " |",
             "| " + " | ".join(["---"] * len(columns)) + " |"]
    for label, (tin, tout, cach, n) in rows:
        cell = [label, fmt_tokens(tin), fmt_tokens(tout),
                fmt_tokens(cach), str(n)]
        if prices:
            if known_model:
                c = cost_of((None, None, label, tin, tout, cach, 0, 0), prices)
                cell.append(f"${c:.4f}" if c is not None else "n/a")
            else:
                cell.append("-")
        lines.append("| " + " | ".join(str(x) for x in cell) + " |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Aggregate token usage and optional cost from ZCode rollout logs.")
    ap.add_argument("--glob", default=DEFAULT_GLOB,
                    help="glob of JSONL rollout files (default: %(default)s)")
    ap.add_argument("--days", type=int, default=0,
                    help="only count turns from the last N days (0 = all)")
    ap.add_argument("--prices", metavar="FILE",
                    help="optional JSON of per-model prices per 1M tokens "
                         "({model: {input, output, cache_read, cache_write}})")
    ap.add_argument("--html", metavar="FILE",
                    help="also write an HTML report to this path")
    ap.add_argument("--limit", type=int, default=10,
                    help="max rows shown per table (default %(default)s)")
    args = ap.parse_args()

    paths = sorted(glob.glob(args.glob))
    if not paths:
        print(f"no rollout files matched: {args.glob}", file=sys.stderr)
        sys.exit(1)
    turns = parse_turns(paths)
    if not turns:
        print("no parseable turns found", file=sys.stderr)
        sys.exit(1)

    if args.days > 0:
        import datetime
        cutoff = (datetime.date.today() - datetime.timedelta(days=args.days)).isoformat()
        turns = [t for t in turns if day_of(t[0]) >= cutoff]
        if not turns:
            print(f"no turns in the last {args.days} days", file=sys.stderr)
            sys.exit(1)

    prices = load_prices(args.prices) if args.prices else None
    per_day, per_sess, per_model, zero_out = aggregate(turns)

    total_in = sum(b[0] for b in per_model.values())
    total_out = sum(b[1] for b in per_model.values())
    total_cach = sum(b[2] for b in per_model.values())
    total_turns = sum(b[3] for b in per_model.values())

    print("# ZCode usage report")
    print("")
    print(f"Files scanned: {len(paths)}")
    print(f"Turns counted: {total_turns}")
    print(f"Tokens: in {fmt_tokens(total_in)} / out {fmt_tokens(total_out)} "
          f"/ cache {fmt_tokens(total_cach)}")
    if zero_out:
        print(f"Note: {zero_out}/{total_turns} turns reported outputTokens=0. "
              "This is a known quirk of some new-api style proxies that omit the "
              "completion count, so output and cost figures are lower bounds in "
              "those cases.")
    if prices:
        cost = sum(cost_of(t, prices) for t in turns
                   if cost_of(t, prices) is not None)
        unm = [m for m in per_model if m not in prices]
        print(f"Estimated cost (models priced): ${cost:.4f}"
              + (f"  (unpriced: {', '.join(sorted(unm)[:5])})" if unm else ""))
    else:
        print("Cost not estimated: pass --prices <file.json> to enable.")
    print("")

    day_rows = sorted(per_day.items(), key=lambda kv: kv[0])
    sess_rows = sorted(per_sess.items(), key=lambda kv: -kv[1][0])
    model_rows = sorted(per_model.items(), key=lambda kv: -kv[1][0])
    cols = ["bucket", "input", "output", "cache", "turns"]
    if prices:
        cols.append("cost")
    print(md_table("Per day", day_rows[-args.limit:], cols, prices, known_model=False))
    print(md_table("Per session", sess_rows[:args.limit], cols, prices, known_model=False))
    print(md_table("Per model", model_rows, cols, prices, known_model=True))

    if args.html:
        rows_html = ""
        for title, rows in (("Per day", day_rows),
                            ("Per session", sess_rows),
                            ("Per model", model_rows)):
            trs = "".join(
                f"<tr><td>{html.escape(str(k))}</td><td>{fmt_tokens(v[0])}</td>"
                f"<td>{fmt_tokens(v[1])}</td><td>{fmt_tokens(v[2])}</td><td>{v[3]}</td></tr>"
                for k, v in rows)
            rows_html += f"<h2>{title}</h2><table><tr><th>bucket</th><th>input</th>" \
                         f"<th>output</th><th>cache</th><th>turns</th></tr>{trs}</table>"
        doc = f"<!doctype html><html><head><meta charset=utf-8>" \
              f"<title>ZCode usage report</title>" \
              f"<style>body{{font-family:system-ui,sans-serif;margin:2rem}}table" \
              f"{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:" \
              f"4px 8px}}th{{background:#eee}}</style></head><body>" \
              f"<h1>ZCode usage report</h1><p>Turns: {total_turns}</p>{rows_html}" \
              f"</body></html>"
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(doc)
        print(f"HTML report written: {args.html}")
    sys.exit(0)


if __name__ == "__main__":
    main()
