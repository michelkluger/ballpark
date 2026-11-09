---
tags: [ballpark]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Bash, WebSearch, WebFetch]
---

I'm about to send this prompt to a Claude Code subagent running Claude Sonnet 5.5 at xhigh effort: "Without using any tools, write a Python function `iso_duration_to_seconds(s: str) -> int` that parses ISO-8601 durations such as 'P3DT4H5M6S', 'PT45M' and 'P1W' (weeks) into seconds. Years and months are not supported and must raise ValueError, as must malformed input. Include 4 doctests. Reply with only the code." It won't use tools, it just replies with the code. /context shows the subagent starts with about 37,000 tokens of system prompt and tool definitions, and Claude Code uses prompt caching. What will this one request cost at API prices? Give me a best estimate and a range.
