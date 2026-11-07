#!/usr/bin/env python3
"""Estimate what an LLM prompt or agent task costs, per model and effort level.

Public data only (models.json): list prices from each provider, and Artificial
Analysis' measured cost per task at each effort level for the token-volume curve.
Stdlib only. Run with --selftest to check the arithmetic.
"""
import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "models.json").read_text(encoding="utf-8"))
MODELS = DATA["models"]
TIERS = {k: v["tokens"] for k, v in DATA["tiers"].items() if not k.startswith("_")}


def prices(m, today, prompt_tokens):
    """$/MTok for one request: applies dated price changes, then the long-context tier."""
    cfg = {**m, **m["then"]} if "then" in m and today >= date.fromisoformat(m["then"]["from"]) else m
    long = cfg.get("long")
    p = long if long and prompt_tokens > long["over"] else cfg["price"]
    return {**p, "cache_write": p.get("cache_write", p["in"])}


def _generic_curve():
    """Median over measured models of cost(level)/cost(high): the fallback effort curve."""
    by = {}
    for m in MODELS.values():
        aa = m.get("aa_cost_per_task", {})
        if "high" in aa:
            for lvl, c in aa.items():
                by.setdefault(lvl, []).append(c / aa["high"])
    curve = {k: v for k, v in DATA["unmeasured_effort_ratio"].items() if not k.startswith("_")}
    return {**curve, **{lvl: statistics.median(v) for lvl, v in by.items()}}


GENERIC = _generic_curve()


def work(m, effort):
    """Token-volume index = AA cost per task / output price, plus how it was derived."""
    aa = m.get("aa_cost_per_task", {})
    if effort in aa:
        return aa[effort] / m["price"]["out"], "measured"
    if aa:
        lvl = "high" if "high" in aa else next(iter(aa))
        return aa[lvl] / m["price"]["out"] / GENERIC[lvl] * GENERIC[effort], "generic curve"
    return REF_WORK * GENERIC[effort], "no AA data"


REF_WORK = work(MODELS[DATA["reference"]["model"]], DATA["reference"]["effort"])[0]


def estimate(m, effort, in_tok, answer, reasoning, turns=1, context=0, growth=0, today=None, caching=False,
             per_call=0, warm=False, fixed_turns=False, read=None):
    """USD for one prompt (turns=1) or an agent loop that re-reads a growing, cached context.

    caching=True: the harness writes the prompt to the cache even on a single call (Claude Code does).
    warm=True: the fixed `context` prefix is already cached (a call with the same system prompt and
    tools ran within the cache lifetime, as with back-to-back agents), so the first call reads it.
    `turns` is the loop length on the reference model at high; like reasoning, it scales with
    the token-volume index, since lower effort also means fewer, more consolidated tool calls.
    fixed_turns=True: the steps are known (a well-specified fix), so `turns` is the call count at any
    effort; only reasoning scales.
    `growth` is tool output added per call (file contents, command output); `read`, if given, is the
    total tool output of the task, spread over the calls instead. Each call's own output (thinking,
    tool-call text, `per_call` tokens of commands and edits) is appended as well, because later
    calls re-read it.
    Returns (usd, output tokens, calls priced).
    """
    today = today or date.today()
    f = work(m, effort)[0] / REF_WORK if effort else 1.0
    caching = caching or warm or turns > 1  # a loop that shrinks to one call at low effort still caches
    # a loop that reads tool output needs a second call to read it, however low the effort
    calls = max(2 if read else 1, round(turns if fixed_turns else turns * f)) if turns > 1 else 1
    if read is not None:  # what an agent reads depends on the code, not on how many calls it takes
        growth = read / max(1, calls - 1)
    out = answer + (reasoning * f if effort else 0) + (per_call * calls if calls > 1 else 0)
    step = growth + out / calls
    usd, base = 0.0, context + in_tok
    for i in range(calls):
        ctx = base + i * step
        p = prices(m, today, ctx)
        if calls == 1 and not caching:
            usd += ctx * p["in"]
        elif i == 0:
            usd += context * p["cached"] + in_tok * p["cache_write"] if warm else ctx * p["cache_write"]
        else:  # earlier context is a cache hit; this call's new tokens are written
            usd += (ctx - step) * p["cached"] + step * p["cache_write"]
        usd += out / calls * p["out"]
    return usd / 1e6, out, calls


def money(x):
    return f"${x:.2f}" if x >= 1 else f"${x:.4f}" if x >= 0.0001 else f"${x:.6f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--file", help="prompt file; tokens estimated per model from characters")
    src.add_argument("--text", help="prompt text; tokens estimated per model from characters")
    src.add_argument("--input-tokens", type=int, help="exact prompt token count (used for every model)")
    ap.add_argument("--context", type=int, default=0, help="extra fixed input: system prompt, tools, attached files")
    ap.add_argument("--answer", type=int, default=500, help="expected visible output tokens (~1.3 per English word)")
    ap.add_argument("--tier", choices=list(TIERS), default="moderate", help="task difficulty -> reasoning tokens")
    ap.add_argument("--reasoning", type=int, nargs="+", metavar="N",
                    help="override: reasoning tokens on the reference model at high; one value, or "
                         "low expected high (measure.py prints the spread of measured runs)")
    ap.add_argument("--model", nargs="*", help="model ids (default: all); prefix match, e.g. 'claude' or 'gpt-6'")
    ap.add_argument("--effort", nargs="*", help="effort levels, or 'all' (default: each model's default)")
    ap.add_argument("--turns", type=int, default=1, help="model calls in an agent loop on Opus 5.5 @ high (default 1)")
    ap.add_argument("--growth", type=int, default=2000,
                    help="tool output added to context per call (file contents, command output); "
                         "the model's own output is added automatically")
    ap.add_argument("--per-call", type=int, default=400,
                    help="visible output per call in agent loops: tool commands, edits, paths (default 400)")
    ap.add_argument("--spread", type=float, default=0.4,
                    help="agent loops: low/high also scale turns and growth by 1-spread / 1+spread (default 0.4)")
    ap.add_argument("--fixed-turns", action="store_true",
                    help="well-specified task with known steps: --turns is the call count at any effort")
    ap.add_argument("--read", type=int,
                    help="total tool output of the task (files read + command output); overrides --growth")
    ap.add_argument("--warm", action="store_true",
                    help="the --context prefix is already cached (same system prompt and tools used within the "
                         "cache lifetime, e.g. back-to-back agents): the first call reads it instead of writing it")
    ap.add_argument("--json", action="store_true", help="print rows as JSON")
    ap.add_argument("--caching", action="store_true",
                    help="harness writes the prompt to the cache even on one call (Claude Code, agent SDKs); "
                         "multi-turn runs always assume caching")
    ap.add_argument("--date", type=date.fromisoformat, default=date.today(), help="price date, YYYY-MM-DD")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    text = Path(a.file).read_text(encoding="utf-8", errors="replace") if a.file else a.text
    if text is None and a.input_tokens is None:
        ap.error("give --file, --text or --input-tokens")
    if a.reasoning is not None and len(a.reasoning) not in (1, 3):
        ap.error("--reasoning takes one value or three (low expected high)")
    r = a.reasoning
    lo, mid, hi = TIERS[a.tier] if r is None else r * 3 if len(r) == 1 else r

    # an exact id means that model only: 'claude-opus-5' must not also pick claude-opus-5-5
    ids = [k for k in MODELS if not a.model or any(k == p if p in MODELS else k.startswith(p) for p in a.model)]
    if not ids:
        ap.error(f"no model matches {a.model}; known: {', '.join(MODELS)}")
    rows, skipped = [], []
    for k in ids:
        m = MODELS[k]
        levels = (m["efforts"] or [None]) if a.effort == ["all"] else a.effort or [m["default"]]
        for e in levels:
            if e is not None and e not in m["efforts"]:
                skipped.append(f"{k}:{e}")
                continue
            tok = a.input_tokens if a.input_tokens is not None else round(len(text) / m["chars_per_token"])
            s = a.spread if a.turns > 1 else 0.0  # loop length and tool output are as uncertain as thinking
            run = lambda r, k: estimate(m, e, tok, a.answer, r, a.turns * k, a.context, a.growth * k, a.date,
                                        a.caching, a.per_call, a.warm, a.fixed_turns,
                                        None if a.read is None else a.read * k)
            (c_lo, *_), (c_mid, out, n), (c_hi, *_) = run(lo, 1 - s), run(mid, 1), run(hi, 1 + s)
            how = work(m, e)[1] if e else "no thinking"
            vol = f"x{work(m, e)[0] / REF_WORK:.2f} ref" if e else "-"
            note = "; ".join(filter(None, [how, m.get("note")]))
            rows.append((c_mid, k, e or "-", tok + a.context, round(out), n, c_lo, c_hi, vol, note))

    rows.sort()
    if a.json:
        keys = ("expected", "model", "effort", "input_tokens", "output_tokens", "calls", "low", "high", "volume", "basis")
        print(json.dumps([dict(zip(keys, r)) for r in rows]))
        return
    head = ("model", "effort", "in tok", "out tok", "turns", "low", "expected", "high", "volume", "basis")
    table = [head] + [(k, e, f"{t:,}", f"{o:,}", str(n), money(l), money(c), money(h), v, b)
                      for c, k, e, t, o, n, l, h, v, b in rows]
    widths = [max(len(r[i]) for r in table) for i in range(len(head))]
    for r in table:
        print("  ".join(s.ljust(w) for s, w in zip(r, widths)).rstrip())

    print(f"\ntier={a.tier if a.reasoning is None else 'custom'} reasoning(ref @ high)={lo:,}/{mid:,}/{hi:,}"
          f"  answer={a.answer:,}  turns={a.turns}" + (f"  growth/turn={a.growth:,}" if a.turns > 1 else ""))
    if text is not None:
        print("input tokens are a character heuristic; pass --input-tokens for an exact count")
    if skipped:
        print(f"skipped (level not supported): {', '.join(skipped)}")
    for k in ids:
        t = MODELS[k].get("then")
        if t and a.date < date.fromisoformat(t["from"]):
            print(f"note: {k} price changes on {t['from']} to ${t['price']['in']}/${t['price']['out']} per MTok")
    age = (a.date - date.fromisoformat(DATA["as_of"])).days
    if age > 45:
        print(f"WARNING: prices are {age} days old (as_of {DATA['as_of']}); refresh models.json from its sources")


def selftest():
    d = date(2026, 11, 7)
    # a made-up model with fixed prices, so refreshing models.json never breaks the arithmetic checks;
    # it has no AA data, so its effort scaling is the generic curve
    fx = {"price": {"in": 4, "cache_write": 5, "cached": 0.2, "out": 20},
          "long": {"over": 200_000, "in": 8, "cached": 0.4, "out": 30},
          "then": {"from": "2027-01-01", "price": {"in": 6, "cached": 0.3, "out": 30}},
          "efforts": ["low", "medium", "high"]}
    # 100k in + 100k out, no thinking: $0.40 + $2
    assert abs(estimate(fx, None, 100_000, 100_000, 0, today=d)[0] - 2.4) < 1e-9
    # the reference model at its reference effort scales reasoning by exactly 1
    ref = MODELS[DATA["reference"]["model"]]
    assert estimate(ref, DATA["reference"]["effort"], 0, 0, 10_000, today=d)[1] == 10_000
    # data check: more effort never costs less, on any model in models.json
    for k, m in MODELS.items():
        costs = [estimate(m, e, 1000, 500, 4000, today=d)[0] for e in m["efforts"]]
        assert costs == sorted(costs), (k, costs)
    # long-context tier and dated price change
    assert prices(fx, d, 250_000)["in"] == 8 and prices(fx, d, 199_000)["in"] == 4
    assert prices(fx, date(2027, 1, 1), 10)["in"] == 6
    # 2-turn loop: turn 1 writes 50k to cache ($5/M), turn 2 reads it ($0.20/M)
    two = estimate(fx, None, 50_000, 0, 0, turns=2, today=d)[0]
    assert abs(two - (50_000 * 5 + 50_000 * 0.2) / 1e6) < 1e-12
    # Claude Code-style single call: the 37k prefix is a cache write ($5/M), not plain input
    one = estimate(fx, None, 37_000, 0, 0, today=d, caching=True)[0]
    assert abs(one - 37_000 * 5 / 1e6) < 1e-12
    # a 2-turn loop that low effort shrinks to 1 call is still priced as a cache write
    shrunk = estimate(fx, "low", 37_000, 0, 0, turns=2, today=d)
    assert shrunk[2] == 1 and abs(shrunk[0] - 37_000 * 5 / 1e6) < 1e-12
    # ...unless it reads tool output: reading needs a second call, so the 1,000 read is still billed
    reads = estimate(fx, "low", 0, 0, 0, turns=2, read=1_000, today=d)
    assert reads[2] == 2 and abs(reads[0] - 1_000 * 5 / 1e6) < 1e-12, reads
    # warm prefix: the 37k system prompt is a cache read ($0.20/M), only the new 1k prompt is written ($5/M)
    warm = estimate(fx, None, 1_000, 0, 0, context=37_000, today=d, warm=True)[0]
    assert abs(warm - (37_000 * 0.2 + 1_000 * 5) / 1e6) < 1e-12
    # well-specified task: the call count does not shrink or grow with effort
    assert estimate(fx, "low", 0, 0, 0, turns=10, fixed_turns=True, today=d)[2] == 10
    # total read spread over the calls: 2,000 over 3 calls -> 1,000 arrives before calls 2 and 3
    spread = estimate(fx, None, 0, 0, 0, turns=3, read=2_000, today=d)[0]
    assert abs(spread - (1_000 * 5 + 1_000 * 0.2 + 1_000 * 5) / 1e6) < 1e-12, spread
    # agent loops: per-call tool text is output; single calls make no tool calls
    assert estimate(fx, None, 0, 0, 0, turns=3, per_call=400, today=d)[1] == 1200
    assert estimate(fx, None, 0, 0, 0, per_call=400, today=d)[1] == 0
    # each call's output joins the context: 300 out over 3 calls -> writes 100+100, reads 100, out 300
    grown = estimate(fx, None, 0, 300, 0, turns=3, today=d)[0]
    assert abs(grown - (200 * 5 + 100 * 0.2 + 300 * 20) / 1e6) < 1e-12, grown
    # lower effort runs a shorter loop
    assert estimate(fx, "low", 0, 0, 0, turns=20, today=d)[2] < estimate(fx, "high", 0, 0, 0, turns=20, today=d)[2]
    # unmeasured model falls back to the reference volume
    assert work(fx, "high") == (REF_WORK, "no AA data")
    print("selftest ok")


if __name__ == "__main__":
    sys.exit(main())
