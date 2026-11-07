# Ballpark

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

Or copy `skills/ballpark/` into `~/.claude/skills/`. Then ask anything about cost ("is it
expensive to run this on Opus?", "which effort level is cheapest for this?") and the skill
triggers. The bundled script runs on its own too:

```bash
python3 skills/ballpark/estimate.py --text "Explain TCP vs UDP" --answer 300 --tier simple
python3 skills/ballpark/estimate.py --input-tokens 12000 --tier hard --model claude-opus-5-5 gpt-6.1 --effort all
python3 skills/ballpark/estimate.py --selftest
```

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

Tested on 2026-11-07 with real Claude Code runs, priced from their transcripts. Agents made
blind predictions, with and without the skill:

| Task | Measured | With Ballpark | Without |
|---|---|---|---|
| Haiku 5.5 @ medium, short explanation | $0.0049 | $0.0052 | $0.0050 |
| Sonnet 5.5 @ xhigh, one function | $0.112 | $0.15 | $0.13 |
| Opus 5.5 @ xhigh, small module + tests (3 calls) | $0.245 | $0.40 | $0.30 |

Every range contained the measured cost and every estimate was within 2×. The skill's answers
also passed more of the other checks: they offered cheaper models or effort levels, and used
the correct prices. On these three dollar estimates, though, the answers without the skill were
closer. The skill overestimated reasoning on routine tasks, and its guidance has since been
corrected. The test cases are in [`skills/ballpark/evals/`](skills/ballpark/evals) and run
with `claude plugin eval`.

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

## Limits

- Not included: tool and search fees, image and audio input, batch and fast tiers.
- Subscription plans (Claude Pro/Max, ChatGPT Plus) are flat-rate, so the estimate is what
  the same work would cost at API prices.
- Cross-model token appetite is only good to about 2×, and a single run can land outside the
  range. For a firm budget, measure 5–10 real runs and pass `--reasoning`.

## Keeping it current

Prices change monthly. To refresh, re-read the URLs in `models.json` → `sources`, update the
rows and run `--selftest`. To add a model, copy a row. Pull requests with refreshed prices are
welcome.

## License

[MIT](LICENSE)
