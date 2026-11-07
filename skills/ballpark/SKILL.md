---
name: ballpark
description: Predict what an LLM prompt, chat request or agent task will cost before running it, for Claude, GPT and Gemini models at each effort / reasoning / thinking level, using only public price lists and public benchmark token data. Use this whenever someone asks how much a prompt or task will cost, which model or effort level is cheapest for a job, whether max/xhigh effort is worth it, how to budget an AI feature or agent run, or wants to compare token costs across providers, even if they don't say "estimate" (e.g. "is it expensive to run this on Opus?", "what would 10k of these cost on GPT?", "should I use low effort for this?").
---

# Ballpark

Turns "what will this cost?" into a number with an honest range. Price lists are exact, but
the bill depends mostly on how many reasoning tokens a model spends, which nobody knows
before the run. So the estimate pairs exact prices with public measurements of how token
spend changes across models and effort levels, and reports low / expected / high.

Everything lives next to this file: `models.json` (prices, effort levels, benchmark data,
and the source URL of every number) and `estimate.py` (Python stdlib only).

## Workflow

**1. Pin down the job.** Is it a single API call, or an agent loop (Claude Code, Codex,
tool-using agents) that calls the model many times? Which models and efforts? If the user
doesn't say, compare every model at its default effort. That is the most useful first view.

**2. Count input tokens.** An exact count beats the character heuristic, which only holds for
English prose (code, JSON and non-English text use more tokens per character):
- Claude: the free `count_tokens` endpoint (`client.messages.count_tokens(...)` or
  `ant messages count-tokens`), when credentials exist. Never use tiktoken for Claude: it
  undercounts by 15-20% or more.
- OpenAI: its own tokenizer (tiktoken). Gemini: the `countTokens` API.
- Otherwise pass the prompt with `--file` / `--text` and the script estimates per model.
Include everything sent: system prompt, attached files, tool definitions (`--context`).

**3. Estimate the visible answer** (`--answer`, tokens): about 1.3 tokens per English word
and about 10 per line of code. Read it from the request: "a 500-word essay" is about 650,
and "fix this function" is about the size of the function. For an agent, count the final
reply plus every file or script it writes, including throwaway scripts that reproduce a bug.
The commands and edits it sends with each tool call are covered by `--per-call` (default 400
tokens per call; measured runs used 360-570).

**4. Pick a difficulty tier** (`--tier`). It sets the reasoning tokens, the biggest unknown:

| tier | reasoning tokens (Opus 5.5 @ high) | typical prompts |
|---|---|---|
| trivial | 0 / 50 / 300 | greeting, lookup, classification, one-line rewrite |
| simple | 200 / 800 / 2.5k | short explanation, summarize given text, small code edit |
| moderate | 1k / 4k / 10k | multi-step reasoning, write a function or module, analyze a doc |
| hard | 5k / 15k / 40k | tricky debugging, proofs, competition math, architecture design |
| frontier | 30k / 60k / 120k | research-grade problems (anchor: AA measured 60.1k/task) |

The tiers and effort multipliers come from hard benchmark tasks. On routine work, models
think far less, even at high effort settings. In a test on 2026-11-07, Opus 5.5 at xhigh
used 376 thinking tokens to write and test a small module, Sonnet 5.5 at xhigh used 1,476
for one function, and Haiku 5.5 at medium used 201 for a short explanation. So rate everyday
coding and writing as `simple`, and save `moderate` and above for work that is actually
hard. Audits, security reviews and debugging that has to reproduce a bug are `hard`: a
repository bug and vulnerability audit on Opus 5.5 at xhigh used 40k thinking tokens. If you
have measured reasoning tokens for this kind of prompt, pass `--reasoning N`.

**5. For agent loops**, add `--turns` (model calls on Opus 5.5 at high), `--context` (fixed
prefix: system prompt, tools, project files; in Claude Code, `/context` shows the real
number) and `--growth` (tool output each call adds: file contents and command output).
Estimate growth from what the agent will read: source code is about 3-4 characters per token,
so add up the sizes of the files it will open, plus test and command output, and divide by
the calls. Don't add the model's own output, because the script appends each call's output,
thinking included, since later calls re-read it. Claude Code starts every subagent with about
37k tokens. When agents run back to back with the same system prompt and tools, within the
5-minute cache lifetime, pass `--warm`. The first call then reads that prefix from the cache
instead of writing it, which saved about $0.18 on Opus 5.5, roughly a quarter of a small fix.
For agent loops, low and high also vary the calls and growth by ±40% (`--spread`).
For a single call through a harness that caches
(Claude Code, agent SDKs), pass `--caching`: the first call writes the prompt to the cache at
1.25× the input price, and in the test above that prefix was most of the bill. The script
assumes prompt caching, and scales turns as well as reasoning by effort, because lower
effort also means fewer, more consolidated tool calls. A SWE-bench-Pro-sized bug fix is
about `--turns 20 --context 2000 --growth 500 --reasoning 1000 --answer 300`. That shape
reproduces Anthropic's published Opus 5.5 cost per task ($0.11 / $0.21 / $0.29 / $0.74 at
low / medium / high / xhigh) within about 13%.

**6. Run it** (`python3`, `python` or `uv run python`, whichever exists):
```bash
python3 <this-skill-dir>/estimate.py --file prompt.txt --answer 800 --tier moderate
python3 <this-skill-dir>/estimate.py --input-tokens 12000 --tier hard --model claude-opus-5-5 gpt-6.1 --effort all
python3 <this-skill-dir>/estimate.py --text "..." --turns 30 --context 20000 --growth 1500 --tier hard --model claude
```
`--model` takes prefixes (`claude`, `gpt-6`, `gemini-3`). `--effort all` sweeps every level.
A level a model doesn't support is skipped and listed. `--date` prices a future day, which
matters because some list prices are already scheduled to change (the script prints those).

**7. Report** in this shape. Keep it short, because a cost estimate is a decision aid:

```
≈ $0.034 per run (range $0.012–$0.09) on claude-opus-5-5 @ medium
At 10,000 runs/month: ≈ $340 ($120–$900)

Cheaper options that likely still fit:  <1-3 rows from the table, with a one-line quality caveat>
Assumptions: <input tokens counted or heuristic>, answer ≈ N tokens, tier = X, <turns if agentic>
Biggest lever: <the one change that saves most: lower effort, smaller model, caching, batch>
```
Scale to the user's volume when they mention one. Name the cost driver (usually reasoning
tokens, or re-read context in agent loops). Mention a model's quality tier when you suggest
it as cheaper: a cheaper model that fails the task is not cheaper. The batch APIs of all three
providers halve the price for work that can wait. Say so when it fits.

## How the numbers are built (for explaining or challenging an estimate)

- **Prices**: each provider's public list price, standard tier, including long-context tiers
  (Haiku 5.5 over 100k, GPT-6 over 272k, Gemini 3.1 Pro over 200k) and scheduled changes.
- **Reasoning volume per model × effort** = Artificial Analysis' measured cost per task ÷ the
  model's output price, relative to Opus 5.5 at high (the `volume` column). Within one
  model this is solid: the effort curve matched Anthropic's own coding measurements. Across
  models it is good to about 2×. On Anthropic's coding benchmark Sonnet 5.5 used fewer
  tokens, and Fable 5.1 more, than AA's broader task mix implies. Models without AA data
  use the median curve and are marked `no AA data` or `generic curve`.
- **Outliers**: a volume like Gemini 3.8 Flash's ×9 comes straight from AA's per-task cost
  and probably reflects heavy agentic input on their benchmark. Flag it as such rather than
  presenting it as certain.

## Keeping it current

Prices and models change monthly. The script warns when `as_of` in `models.json` is more
than 45 days old. To refresh, re-read each URL in `sources` and update the rows. To add a
model, copy a row: `price` (USD per million tokens), `efforts`, `default`, `chars_per_token`,
and optionally `long`, `then` and `aa_cost_per_task` from the Artificial Analysis leaderboard.
Then run `python3 estimate.py --selftest`.

## Limits (say so when they matter)

- Not included: tool or search fees, images/audio/video input, fast/priority/batch tiers,
  regional-processing uplifts, Gemini explicit-cache storage.
- Subscription plans (Claude Pro/Max, ChatGPT Plus, Gemini Advanced) are flat-rate. The
  estimate is then the API-equivalent cost, useful as a measure of how heavy a task is.
- Effort is a behavioral signal, not a hard budget. One run can land far outside the range.
  For real budgeting, run 5-10 representative prompts, read `usage` from the responses, and
  pass the measured reasoning tokens via `--reasoning`.
