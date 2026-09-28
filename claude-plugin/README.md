# WoS Porter — Claude Code plugin

Automatically ports open-source **x64 Windows applications to native ARM64** (aarch64-pc-windows-msvc). The plugin orchestrates a pipeline of specialized sub-agents that analyze a repo, port the build system and source, resolve ARM64 dependencies, build, validate binaries with `dumpbin`, run tests, and apply hand-written `<arm_neon.h>` optimizations.

This is the Claude Code packaging of the `wos-porter` VS Code extension — the same agent/skill/reference content, converted to Claude Code plugin conventions.

## What's inside

- **commands/** — `/wos-porter:wos-porter <repo-url>` — the entry-point orchestrator that runs the 8-phase pipeline in the main loop. `/wos-porter:wos-etl-hotspot` — ETL trace hotspot analyzer and ARM64 optimizer.
- **agents/** — the `wos-porter` pipeline instructions plus 7 sub-agents (`wos-analyzer`, `wos-build-porter`, `wos-code-porter`, `wos-builder`, `wos-tester`, `wos-optimizer`, `wos-etl-hotspot`) spawned by the orchestrator.
- **prompts/** — `wos-verify-port.prompt.md`, the Phase 8 verification gate the orchestrator reads and runs inline.
- **skills/** — 11 auto-loading skills (NEON reference, toolchain discovery, SSE/AVX→NEON translation, build-error recipes, WoA dashboard, etc.).
- **references/** — porting-knowledge docs and per-build-system recipes loaded on demand by the agents.

## Prerequisites

- **Claude Code** installed and authenticated (`claude` on your PATH, or the VS Code / JetBrains extension).
- **Windows host** (x64 or ARM64) with **Visual Studio 2022** and these components:
  - **MSVC v143 - ARM64/ARM64EC build tools (Latest)**
  - **Windows 11 SDK**
- **git** on PATH.

The target is always Windows ARM64; the host may be x64 (cross-compile) or ARM64 (native build + test).

## Installation

There are three ways to install, depending on where the plugin lives. Pick one.

### Option A — Interactive menu (recommended)

https://github.com/user-attachments/assets/068e688f-3d6f-4fdf-a4e8-d026dce2ed82


**Using the VS Code UI**
If you prefer using the UI instead of typing commands, install the Claude Code extension for Visual Studio Code, then open a new session and run:

```
/plugin
```

Then choose **Manage marketplaces → Add marketplace**, enter `qualcomm/extension-wos-porter` (or a local path), and install **wos-porter** from the browse list.


### Option B — Install from a local clone

Use this while developing, or when you have the repo checked out locally.

1. Clone (or use your existing checkout):

   ```
   git clone https://github.com/qualcomm/extension-wos-porter.git
   ```

2. In Claude Code, add the local checkout as a marketplace (point at the repo root that contains `.claude-plugin/marketplace.json`):

   ```
   /plugin marketplace add C:\path\to\extension-wos-porter
   ```

3. Install:

   ```
   /plugin install wos-porter@extension-wos-porter
   ```

### Option C — Install from GitHub


This works once the repo (including the root `.claude-plugin/marketplace.json` and this `claude-plugin/` folder) is pushed to GitHub.

1. Open Claude Code in any project.
2. Add the marketplace (the repo that advertises the plugin):

   ```
   /plugin marketplace add qualcomm/extension-wos-porter
   ```

   If the plugin is on a non-default branch, pin it:

   ```
   /plugin marketplace add qualcomm/extension-wos-porter@refactor
   ```

3. Install the plugin from that marketplace:

   ```
   /plugin install wos-porter@extension-wos-porter
   ```

4. Verify it loaded:

   ```
   /plugin
   ```

   You should see **wos-porter** listed as enabled. The `/wos-porter:wos-porter`, `/wos-porter:wos-etl-hotspot`, and `/wos-porter:x64-benchmarker` commands and the `wos-*` sub-agents are now available.

To update later, refresh the marketplace and reinstall:

```
/plugin marketplace update extension-wos-porter
/plugin install wos-porter@extension-wos-porter
```

## Using with Codex CLI

The same plugin works in **OpenAI Codex CLI** — the `.claude-plugin/marketplace.json` and `claude-plugin/` directory are already in the Codex plugin format.

### Install

1. Add the repo as a Codex marketplace (run once, from any directory):

   ```
   codex plugin marketplace add C:\path\to\extension-wos-porter
   ```

   Or from GitHub (once the repo is public):

   ```
   codex plugin marketplace add qualcomm/extension-wos-porter
   ```

2. Install the plugin:

   ```
   codex plugin add wos-porter@extension-wos-porter
   ```

### Use

```
@wos-porter https://github.com/owner/repo
```

Optional flags work exactly as in Claude Code — pass inline in your message:

```
# Skip NEON optimization:
@wos-porter https://github.com/owner/repo WOS_SKIP_OPTIMIZE=1

# x64 baseline for gap-targeted optimization:
@wos-porter https://github.com/owner/repo C:\x64_bench\bench_results.json
```

### Update

```
codex plugin marketplace update extension-wos-porter
codex plugin add wos-porter@extension-wos-porter
```

---

## Usage

Run the orchestrator command and pass a GitHub repository URL to port:

```
/wos-porter:wos-porter https://github.com/owner/repo
```

Example:

```
/wos-porter:wos-porter https://github.com/facebook/zstd
```

This command runs the full **8-phase pipeline in the main conversation** — it reads the `wos-porter` agent's instructions and spawns the six sub-agents (`wos-analyzer`, `wos-build-porter`, `wos-code-porter`, `wos-builder`, `wos-tester`, `wos-optimizer`) itself. It runs in the main loop because sub-agents cannot spawn further sub-agents.

What happens, end to end:

1. **Setup** — clones the repo and creates an `arm64-port` branch.
2. **Analysis** — `wos-analyzer` scans ARM64 readiness (build systems, SIMD/asm, deps, CI).
3. **Porting** — `wos-build-porter` + `wos-code-porter` add ARM64 build targets and arch guards.
4. **Dependencies** — discovers the toolchain and resolves ARM64 target dependencies.
5. **Build** — `wos-builder` builds for ARM64, fixes errors, validates binaries with `dumpbin`.
6. **Test** — `wos-tester` runs tests/benchmarks (native on ARM64 hosts; deferred on x64 hosts).
7. **NEON optimization** — `wos-optimizer` applies hand-written `<arm_neon.h>` intrinsics behind ARM64 guards.
8. **Report** — verifies every claim against disk (the G1–G8 gates in [prompts/wos-verify-port.prompt.md](prompts/wos-verify-port.prompt.md)), writes `ARM64-PORT.md`, and prints a summary.

The ported code stays **local** on the `arm64-port` branch — nothing is pushed, and `main`/`master` is never modified.

### ETL trace hotspot analysis and ARM64 optimization

Use this command when you already have a built application and an ETL trace from a representative workload and want ARM64 optimizations focused on the functions that actually dominate that workload.

**Prerequisites (additional to the base prerequisites above):**

- **Windows Performance Toolkit** — `wpaexporter.exe` on PATH (installed with the Windows ADK, or via the Windows Performance Toolkit standalone download).
- A built application `.exe` and matching `.pdb` file(s).
- An ETL trace (`.etl`) captured from a representative workload run.

**Command:**

```
/wos-porter:wos-etl-hotspot <exe> <pdb> <etl> <source-dir>
```

| Argument | Description |
|---|---|
| `<exe>` | Absolute path to the application executable, e.g. `C:\build\myapp.exe` |
| `<pdb>` | Absolute path to the PDB file or a folder containing PDB files |
| `<etl>` | Absolute path to the ETL trace, e.g. `C:\traces\scenario.etl` |
| `<source-dir>` | Absolute path to the application source tree |

**Example:**

```
/wos-porter:wos-etl-hotspot C:\build\sqlite3.exe C:\build\sqlite3.pdb C:\traces\query_workload.etl C:\src\sqlite
```

**What happens, end to end:**

1. Runs `hotspot_analysis.py` against the ETL trace — generates a SymCache from the PDB, exports CPU sampling data via `wpaexporter`, and cross-references the top hotspot functions against the source tree.
2. Reads the full source body of each hotspot function and traces its transitive callees.
3. Applies the most effective Windows ARM64 optimizations to each hotspot and its dependent functions — NEON/SVE/SVE2/SME vector extensions, scalar and micro-architectural tuning, branch/prefetch/memory-layout improvements, or compiler-flag changes — guarded and correctness-first.
4. Delegates the ARM64 build to the `wos-builder` sub-agent.
5. Delegates test and validation to the `wos-tester` sub-agent.
6. Writes a detailed HTML report into `<source-dir>` documenting every hotspot, its transitive callees, the optimization applied (or why not), the exact code changes, and build/test results.

### Controlling the work directory (optional)

By default the pipeline clones into `C:\src\wos-porter\<repo>`. Override it by setting `WOS_PORTER_WORKDIR` before launching Claude Code:

```powershell
$env:WOS_PORTER_WORKDIR = "D:\ports"
```

## Uninstall

```
/plugin uninstall wos-porter@extension-wos-porter
```

To also remove the marketplace entry:

```
/plugin marketplace remove extension-wos-porter
```

## Troubleshooting

- **`/wos-porter:wos-porter` isn't recognized** — confirm the plugin is enabled with `/plugin`. If it's missing, re-run the install step.
- **`/wos-porter:wos-etl-hotspot` isn't recognized** — reinstall the plugin to pick up the new command: `/plugin uninstall wos-porter@extension-wos-porter` then re-run the install step.
- **`wpaexporter` not found** — install the Windows Assessment and Deployment Kit (ADK) and ensure `wpaexporter.exe` is on your PATH. It is part of the **Windows Performance Toolkit** component.
- **Marketplace add fails from GitHub** — make sure the plugin files and the root `.claude-plugin/marketplace.json` are committed and pushed to the branch you're pointing at (Claude Code reads the pushed tree, not your local working copy). Pin the branch with `@<branch>` if it isn't on the default branch.
- **Build phase reports missing toolchain** — install the **MSVC v143 - ARM64/ARM64EC build tools** and **Windows 11 SDK** via the Visual Studio Installer, then retry.
