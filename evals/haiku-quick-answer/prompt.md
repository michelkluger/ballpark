---
tags: [ballpark]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Bash, WebSearch, WebFetch]
---

I'm about to send this prompt to a Claude Code subagent running Claude Haiku 5.5 at medium effort: "Explain the difference between TCP and UDP in about 200 words, with one concrete example of where each is used." It won't use any tools, it just answers. /context shows the subagent starts with about 37,000 tokens of system prompt and tool definitions, and Claude Code uses prompt caching. What will this one request cost at API prices? Give me a best estimate and a range.
