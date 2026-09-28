# ETL Hotspot Optimization

Use the `wos-etl-hotspot` agent when you have a representative Windows performance trace (`.etl`) for your application. Instead of optimizing speculatively, the agent reads the trace to identify exactly which functions dominate CPU time, then applies ARM64 optimizations only to those hotspots and their dependent callees.

## What It Does

1. Runs `hotspot_analysis.py` against your `.exe`, `.pdb`, and `.etl` to extract the top-20 CPU-hottest functions matched to source code
2. Reads each function body and walks the transitive call graph to find all in-source dependent callees
3. Applies the full range of ARM64 optimizations — NEON/SVE/SVE2/SME vectorization, scalar/branch/memory tuning, build-flag improvements — to every hotspot and callee
4. Delegates the ARM64 build to the `wos-builder` sub-agent and test/validation to the `wos-tester` sub-agent
5. Writes a self-contained `ARM64-Optimization-Report.html` into your source directory

## Required Inputs

The agent will ask for any of these that are missing before starting:

| Input | Description | Example |
|-------|-------------|---------|
| `.exe` path | Absolute path to the built application executable | `C:\build\myapp.exe` |
| `.pdb` path or folder | Absolute path to the matching `.pdb` file, or a folder containing `.pdb` files | `C:\build\myapp.pdb` |
| `.etl` path | Absolute path to the ETL scenario trace file | `C:\traces\scenario.etl` |
| Source directory | Absolute path to the application source tree | `C:\src\myapp` |

> The `.exe` and `.pdb` must be from the **same build** (matching PDB GUID). The ETL trace should represent a real workload scenario — not idle time or synthetic noise.

## Prerequisites

The agent auto-installs missing tools via `winget` before starting:

| Tool | Auto-installed if missing |
|------|--------------------------|
| Python 3 | `winget install Python.Python.3` |
| Windows ADK / Windows Performance Toolkit (`symcachegen.exe`, `wpaexporter.exe`) | `winget install Microsoft.WindowsADK` |

## GitHub Copilot (VS Code Extension)

Install the VSIX (see [Copilot installation](copilot-installation.md)), then open Copilot Chat and type:

```
@wos-etl-hotspot
```

Copilot Chat will prompt for the four inputs and run the full pipeline.

The VS Code extension copies `hotspot_analysis.py` to `~/.copilot/agents/etl_hotspot_tool/` automatically on install — no manual setup needed.

## Claude Code (Plugin)

Install the Claude Code plugin (see [Claude plugin README](../claude-plugin/README.md)), then run:

```
@wos-etl-hotspot
```

`hotspot_analysis.py` is bundled inside the plugin and resolved automatically from `~/.claude/plugins/wos-porter/etl_hotspot_tool/` after `claude plugin add wos-porter@extension-wos-porter`.

## Codex CLI (Plugin)

Install the Codex plugin (see [Codex plugin README](../codex-plugin/README.md)), then run:

```
@wos-etl-hotspot
```

`hotspot_analysis.py` is at `etl_hotspot_tool/hotspot_analysis.py` in the repo root, which is accessible automatically because the Codex marketplace registers the full repo.

## Output

The agent writes `ARM64-Optimization-Report.html` into your source directory. The report contains:

- **Executive summary** — hotspots analyzed, functions optimized, binaries validated, tests passed
- **Top-N hotspot table** — rank, function, file:line, CPU weight, CPU %, and optimization disposition
- **Callee dependency map** — transitive in-source callees for each hotspot, with depth
- **Per-function before/after diffs** — exact code changes with intrinsics used and correctness notes
- **Not-optimized reasons** — every function where vectorization was not applicable, with the documented serial-dependency reason
- **Build results** — `dumpbin` machine-type confirmation (`AA64`) for every binary
- **Test results** — pass/fail counts and benchmark deltas from `wos-tester`

## When to Use This

| Scenario | Recommendation |
|----------|---------------|
| You have an ETL trace for a real workload | Use `@wos-etl-hotspot` — optimization targets the actual bottlenecks |
| No ETL trace available | Use the standard porter (`@wos-porter`) with coverage-driven optimizer |
| You want ARM64 vs x64 performance comparison | Use the [x64 Competitive Analysis](x64-competitive-analysis.md) workflow instead (or in addition) |
| You only need a working port, no optimization | Set `WOS_SKIP_OPTIMIZE=1` — see [Skip Optimization](skip-optimization.md) |
