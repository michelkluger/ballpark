#!/usr/bin/env python3
"""Measure what Claude Code runs actually cost, and turn them into estimate.py inputs.

  measure.py <transcript.jsonl> [...]

Claude Code keeps one JSONL transcript per session under ~/.claude/projects/<project>/ and one per
subagent under <session>/subagents/. Each call is priced with models.json at today's prices, so
measurement and estimate share one price list. With two or more runs of the same model it prints
the median inputs to pass to estimate.py, so estimates for similar work converge on your own runs.
"""
import json
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from estimate import DATA, MODELS, REF_WORK, prices, work


def measure(path):
    calls, seen, efforts = [], set(), Counter()
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        if effort := (msg.get("output_config") or {}).get("effort"):
            efforts[effort] += 1
        u = msg.get("usage")
        # "<synthetic>" lines are Claude Code's own notices (errors, interrupts), not model calls
        if rec.get("type") != "assistant" or not u or msg.get("model") == "<synthetic>":
            continue
        key = msg.get("id") or rec.get("uuid")  # one response spans several transcript lines
        if key in seen:
            continue
        seen.add(key)
        calls.append((msg.get("model"), u))
    if not calls:
        return None
    usd, out, think, ctxs, first_read = 0.0, 0, 0, [], None
    for model, u in calls:
        if model not in MODELS:
            raise SystemExit(f"{path}: model {model!r} is not in models.json")
        cc = u.get("cache_creation") or {}
        w5 = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0))
        w1 = cc.get("ephemeral_1h_input_tokens", 0)
        inp, rd, o = u.get("input_tokens", 0), u.get("cache_read_input_tokens", 0), u.get("output_tokens", 0)
        ctxs.append(inp + rd + w5 + w1)
        first_read = rd if first_read is None else first_read
        p = prices(MODELS[model], date.today(), ctxs[-1])
        usd += (inp * p["in"] + w5 * p["cache_write"] + w1 * 2 * p["in"] + rd * p["cached"] + o * p["out"]) / 1e6
        out += o
        think += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0)
    n = len(calls)
    model = Counter(c[0] for c in calls).most_common(1)[0][0]
    effort = efforts.most_common(1)[0][0] if efforts else None
    return {"file": Path(path).name, "model": model, "effort": effort, "calls": n, "usd": usd,
            "context": ctxs[0], "prefix": first_read, "warm": first_read > ctxs[0] / 2, "thinking": think, "visible": out - think,
            # context growth minus the model's own output (which stays in context) = tool output read
            "read": max(0, round(ctxs[-1] - ctxs[0] - out * (n - 1) / n))}


def main(paths):
    runs = [r for r in map(measure, paths) if r]
    if not runs:
        raise SystemExit("no usage records found")
    print(f"{'run':40} {'model':18} {'effort':7} {'calls':>5} {'cost':>8} {'thinking':>9} {'visible':>8} {'read':>8}")
    for r in runs:
        print(f"{r['file'][:40]:40} {r['model']:18} {r['effort'] or '-':7} {r['calls']:5} ${r['usd']:7.3f} "
              f"{r['thinking']:9,} {r['visible']:8,} {r['read']:8,}  {'warm' if r['warm'] else 'cold'}")
    same = [r for r in runs if r["model"] == runs[0]["model"]]
    if len(same) < 2:
        return
    m = MODELS[runs[0]["model"]]
    med = lambda f: round(statistics.median(f(r) for r in same))  # noqa: E731
    at_high = sorted(r["thinking"] * REF_WORK / work(m, r["effort"])[0] if r["effort"] else r["thinking"] for r in same)
    reasoning = f"{round(at_high[0])} {round(statistics.median(at_high))} {round(at_high[-1])}"  # spread, not a point
    print(f"\n{len(same)} runs of {runs[0]['model']}: median cost ${statistics.median(r['usd'] for r in same):.3f}")
    # the first call's input already holds the prompt: what came from the cache is --context,
    # the rest (prompt, plus the prefix on a cold start) is --input-tokens, so nothing counts twice
    print(f"inputs for similar work:  --input-tokens {med(lambda r: r['context'] - r['prefix'])} "
          f"--context {med(lambda r: r['prefix'])} --turns {med(lambda r: r['calls'])} --fixed-turns "
          f"--read {med(lambda r: r['read'])} --reasoning {reasoning} "
          f"--answer 0 --per-call {med(lambda r: r['visible'] / r['calls'])}"
          + (" --warm" if sum(r["warm"] for r in same) > len(same) / 2 else ""))


def selftest():
    import tempfile
    model = DATA["reference"]["model"]
    first = {"type": "assistant", "message": {"id": "a", "model": model, "usage": {
        "input_tokens": 0, "cache_creation_input_tokens": 37_000, "cache_read_input_tokens": 0,
        "output_tokens": 1_000, "output_tokens_details": {"thinking_tokens": 600}}}}
    second = {"type": "assistant", "message": {"id": "b", "model": model, "usage": {
        "input_tokens": 0, "cache_creation_input_tokens": 500, "cache_read_input_tokens": 38_000,
        "output_tokens": 200}}}
    synthetic = {"type": "assistant", "message": {"id": "s", "model": "<synthetic>", "usage": {
        "input_tokens": 0, "output_tokens": 0}}}
    request = {"type": "api-request-blob", "message": {"output_config": {"effort": "xhigh"}}}
    lines = [request, first, first, synthetic, second]  # the duplicate line is one response split in two
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(map(json.dumps, lines)))
    r = measure(f.name)
    Path(f.name).unlink()
    assert r["calls"] == 2 and r["effort"] == "xhigh" and not r["warm"] and r["prefix"] == 0, r
    p = prices(MODELS[model], date.today(), 0)  # priced from models.json, so a price refresh keeps this green
    assert abs(r["usd"] - ((37_000 + 500) * p["cache_write"] + 38_000 * p["cached"] + 1_200 * p["out"]) / 1e6) < 1e-12, r
    assert r["thinking"] == 600 and r["visible"] == 600 and r["read"] == 38_500 - 37_000 - 600, r
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main(sys.argv[1:]) if sys.argv[1:] else print(__doc__)
