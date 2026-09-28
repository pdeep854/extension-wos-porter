# WoS Porter — Codex plugin

This repo contains the **wos-porter** plugin, which ports open-source x64 Windows applications to native ARM64.

## Install the plugin (one-time)

**Option A — from a local clone:**

```
codex plugin marketplace add C:\path\to\extension-wos-porter
codex plugin add wos-porter@extension-wos-porter
```

**OR**

**Option B — from GitHub:**

```
codex plugin marketplace add qualcomm/extension-wos-porter
codex plugin add wos-porter@extension-wos-porter
```

> **Note:** Restart Codex after installing for the plugin to take effect.

## Usage

### Port a GitHub repo to ARM64

```
@wos-porter https://github.com/owner/repo
```

This runs the full 8-phase pipeline: clone → analyze → port build + source → resolve deps → build → test → NEON optimize → report.

#### Optional flags

Pass inline in your message — no environment setup needed:

```
# Skip NEON optimization (phases 1–6 + 8 only, fewer tokens):
@wos-porter https://github.com/owner/repo WOS_SKIP_OPTIMIZE=1

# Use an x64 baseline for gap-targeted NEON optimization:
@wos-porter https://github.com/owner/repo C:\x64_bench\bench_results.json
```

Or set environment variables before running:

```powershell
$env:WOS_SKIP_OPTIMIZE = '1'                          # skip Phase 7
$env:WOS_X64_BENCH = 'C:\x64_bench\bench_results.json' # x64 baseline
```

### Optimize hotspots from an ETL scenario trace

Use `@wos-etl-hotspot` when you have a representative Windows performance trace (`.etl`) and want to focus ARM64 optimizations on the functions that actually dominate that workload:

```
@wos-etl-hotspot
```

The agent will ask for four inputs:

| Input | Description |
|-------|-------------|
| `.exe` path | Absolute path to the built application executable |
| `.pdb` path | Absolute path to the matching `.pdb` file or a folder containing `.pdb` files |
| `.etl` path | Absolute path to the ETL scenario trace file |
| Source directory | Absolute path to the application source tree |

**What it does:**
1. Runs `hotspot_analysis.py` to extract top-20 CPU-hottest application functions from the trace.
2. Reads each function body and walks the transitive call graph to find in-source dependent callees.
3. Applies ARM64 optimizations (NEON/SVE/SVE2/SME vectorization, scalar/branch/memory tuning, build flags) to every hotspot and callee.
4. Delegates the ARM64 build to `wos-builder` and test/validation to `wos-tester`.
5. Writes a self-contained `ARM64-Optimization-Report.html` into the source directory.

**Prerequisites:**
- Python 3 on PATH (auto-installed via `winget` if missing)
- Windows ADK / Windows Performance Toolkit (`symcachegen.exe`, `wpaexporter.exe`) — auto-installed via `winget` if missing
- The `.exe` and `.pdb` must be from the same build (matching PDB GUID)

**How `hotspot_analysis.py` is located:**

`hotspot_analysis.py` lives at `etl_hotspot_tool/hotspot_analysis.py` in the repo root — it is available automatically because the Codex plugin marketplace registers the entire repo. The agent resolves it from the marketplace/clone root; no separate copy inside `codex-plugin/` is needed.

## Uninstall

```
codex plugin remove wos-porter@extension-wos-porter
codex plugin marketplace remove extension-wos-porter
```

## Output

The pipeline writes an `ARM64-PORT.md` report to the ported repo and produces a `git format-patch` series on the `arm64-port` branch.

