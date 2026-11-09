---
tags: [ballpark]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Bash, WebSearch, WebFetch]
---

I'm going to hand this task to a Claude Code subagent running Claude Opus 5.5 at xhigh effort: "Create a small Python project in a new folder: a module wordfreq.py with `top_words(text: str, n: int) -> list[tuple[str, int]]` (case-insensitive, ignores punctuation, ties broken alphabetically) and a pytest file with 3 tests. Run the tests with `uv run --with pytest pytest -q` and make them pass. Report the final test output." It will use tools (write files, run pytest). /context shows the subagent starts with about 37,000 tokens of system prompt and tool definitions, and Claude Code uses prompt caching. Roughly what will the whole task cost at API prices? Give me a best estimate and a range.
