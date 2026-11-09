# Ballpark

[![selftest](https://github.com/michelkluger/ballpark/actions/workflows/selftest.yml/badge.svg)](https://github.com/michelkluger/ballpark/actions/workflows/selftest.yml)

A Claude Code skill that tells you what an LLM prompt or agent task will cost **before** you
run it: per model, per effort level, as a low / expected / high range in dollars.

```
> /ballpark:ballpark what will this refactor cost on Opus vs Sonnet?

≈ $0.30 per run (range $0.27–$0.35) on claude-opus-5-5 @ xhigh
Cheaper options that likely still fit: Opus 5.5 @ medium ≈ $0.23, Sonnet 5.5 @ high ≈ $0.13
Biggest lever: the 37k-token Claude Code prefix is most of the bill
```

It covers Claude (Fable, Opus, Sonnet, Haiku), OpenAI's GPT-6 family and Google's Gemini, at
every effort, reasoning or thinking level each provider offers. It works for single API calls
and for agent loops that re-read a growing, cached context.

## Install

As a plugin (in Claude Code):

```
/plugin marketplace add michelkluger/ballpark
/plugin install ballpark@ballpark
```

To update later, run `claude plugin marketplace update ballpark` and
`claude plugin update ballpark@ballpark`, then restart Claude Code.

Or copy `skills/ballpark/` into `~/.claude/skills/`. Then ask anything about cost ("is it
expensive to run this on Opus?", "which effort level is cheapest for this?") and the skill
triggers. The bundled script runs on its own too:

```bash
python3 skills/ballpark/estimate.py --text "Explain TCP vs UDP" --answer 300 --tier simple
python3 skills/ballpark/estimate.py --input-tokens 12000 --tier hard --model claude-opus-5-5 gpt-6.1 --effort all
python3 skills/ballpark/measure.py ~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl
python3 skills/ballpark/estimate.py --selftest
```

`measure.py` prices finished Claude Code runs from their transcripts, either main sessions or
subagents. Given two or more runs of one model, it prints the `estimate.py` inputs to use for
the next similar task.

The skill passes prompts to the script in a file, never as text on the command line. That way
a pasted prompt containing `$(...)` or backticks can't run as a shell command.

Python 3 standard library only, no dependencies.

## How it estimates

The bill depends mostly on how many reasoning tokens a model spends, which nobody knows
before the run. Ballpark combines:

- **List prices** from each provider's public price page, including long-context tiers,
  cache read/write prices and price changes that are already announced.
- **Effort curves** from [Artificial Analysis](https://artificialanalysis.ai/leaderboards/models):
  measured cost per task for each model at each effort level. Within one model, this matched
  Anthropic's own published effort costs within about 10%.
- **A difficulty tier** (trivial → frontier) that the model picks from the prompt, plus the
  expected answer length.

Every number in [`models.json`](skills/ballpark/models.json) carries its source URL and an
`as_of` date. The script warns when the prices are more than 45 days old.

## How accurate is it?

Three real Claude Code runs were priced from their transcripts on 2026-11-07. On 2026-11-09,
Opus 5.5 agents predicted each cost blind with v0.4.3: three agents with the skill and three
without it, per task. The table shows the median best estimate and how far it was from the
measured cost, plus the median width of the predicted range (high ÷ low):

| Task | Measured | With Ballpark | Range width | Without | Range width |
|---|---|---|---|---|---|
| Haiku 5.5 @ medium, short explanation | $0.0049 | $0.0050 (1.01×) | 1.4× | $0.0050 (1.01×) | 16× |
| Sonnet 5.5 @ xhigh, one function | $0.112 | $0.115 (1.03×) | 1.6× | $0.13 (1.16×) | 10× |
| Opus 5.5 @ xhigh, small module + tests (3 calls) | $0.245 | $0.32 (1.30×) | 1.7× | $0.45 (1.83×) | 5× |

With the skill, the best estimate was as close or closer on every task, and the ranges were
3–11× narrower. Without the skill, every range contained the measured cost, but only because
the ranges were wide: $0.0005–$0.009 for a call that cost $0.005. With the skill, 6 of 9
ranges contained it. The 3 misses were all on the Opus task: each range started at $0.25–$0.27,
just above the $0.245 measured. The agents assumed 4–10 model calls, but the real run took 3.
One skill run listed the eval folder, whose file names include the measured cost. Leaving that
run out moves the Opus median to $0.33.

The first test, on 2026-11-07, used an earlier version and one prediction per task. There the
answers without the skill were closer (Sonnet: $0.13 without, $0.15 with; Opus: $0.30 without,
$0.40 with), because the skill overestimated reasoning on routine work. That guidance has since
been corrected. The test cases are in [`evals/`](evals) for `claude plugin eval`. The runner only
grants a shell inside a sandbox, and Windows doesn't have one yet, so these runs used Claude
Code subagents with the same prompts.

**Backlog test, 2026-11-07.** Fifteen agent fixes ran one after another on a real
Python/TypeScript repository (Opus 5.5 @ xhigh in Claude Code). Each was predicted before it
started and measured from its transcript afterwards:

| | Fixes | Bias | Median error | In range | Total predicted vs actual |
|---|---|---|---|---|---|
| Inputs guessed from the task | 6 | 1.19× (over) | 1.26× | 6/6 | $4.15 vs $3.47 |
| Inputs from `measure.py` on earlier runs | 9 | 0.92× | 1.21× | 6/9 | $3.96 vs $4.52 |
| All | 15 | 1.02× | 1.21× | 12/15 | **$8.10 vs $7.99** |

The backlog total landed within 1.4% of the actual cost, and measured inputs removed the
overestimate. A single fix still misses by about 20% on a typical run, and by up to 2×
when it differs from the runs it was calibrated on. That happened three times: a harder
fix that thought 4× the median, a one-file change, and a change that needed online lookups.
Thinking per fix ranged from 0.8k to 17k tokens even within one kind of work.

These runs used v0.4.2. In v0.4.3, `measure.py` prices the part of a warm start that wasn't
cached as a cache write instead of a cache read. That raises its measured-input estimates, so
the 0.92× bias in the table predates the fix.

## Limits

- Not included: tool and search fees, image and audio input, batch and fast tiers.
- Subscription plans (Claude Pro/Max, ChatGPT Plus) are flat-rate, so the estimate is what
  the same work would cost at API prices.
- Cross-model token appetite is only good to about 2×, and a single run can land outside the
  range. For a firm budget, measure 5–10 real runs and pass `--reasoning`.

## Keeping it current

Prices change monthly. To refresh, re-read the URLs in `models.json` → `sources` and update the
rows. To add a model, copy a row. Then run `estimate.py --selftest` and `measure.py --selftest`.
CI also runs both on every push and pull request. The tests use their own fixed prices, so a
refresh only fails them if the arithmetic breaks or the data stops making sense (more effort
must never cost less). Pull requests with refreshed prices are welcome.

## License

[MIT](LICENSE)
