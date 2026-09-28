---
description: "Analyze an ETL scenario trace for a built application: detect CPU-hottest functions, cross-reference with source, apply Windows ARM64 optimizations (NEON/SVE/SVE2/SME, scalar tuning, branch/memory improvements), delegate build and test to sub-agents, and write an HTML report."
argument-hint: "<.exe path> <.pdb path or folder> <.etl trace path> <source directory>"
---

You are now acting as the **wos-etl-hotspot** agent, running directly in this main conversation (NOT as a spawned subagent). This is required because subagents on this Claude Code version cannot spawn further subagents — so YOU, the main agent, must invoke the sub-agents yourself.

## Steps

1. Read your full operating instructions from `${CLAUDE_PLUGIN_ROOT}/agents/wos-etl-hotspot.md`. Follow that agent's entire pipeline verbatim as if those instructions were your own system prompt. Ignore its YAML frontmatter (name/description/tools/agents) — just execute the body.

2. When those instructions tell you to invoke a sub-agent (`wos-builder` or `wos-tester`), spawn it with the **Agent** tool using the matching `subagent_type` — i.e. `subagent_type: "wos-builder"` or `subagent_type: "wos-tester"`. These are first-level subagent spawns from the main loop, which is supported.

## Input

$ARGUMENTS
