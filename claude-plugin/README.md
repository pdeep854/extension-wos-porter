# WoS Porter — Claude Code plugin

Automatically ports open-source **x64 Windows applications to native ARM64** (aarch64-pc-windows-msvc). The plugin orchestrates a pipeline of specialized sub-agents that analyze a repo, port the build system and source, resolve ARM64 dependencies, build, validate binaries with `dumpbin`, run tests, and apply hand-written `<arm_neon.h>` optimizations.

This is the Claude Code packaging of the `wos-porter` VS Code extension — the same agent/skill/reference content, converted to Claude Code plugin conventions.

## What's inside

- **commands/** — `/wos-porter:wos-porter <repo-url>` — the entry-point orchestrator that runs the 8-phase pipeline in the main loop.
- **agents/** — the `wos-porter` pipeline instructions plus 6 sub-agents (`wos-analyzer`, `wos-build-porter`, `wos-code-porter`, `wos-builder`, `wos-tester`, `wos-optimizer`) spawned by the orchestrator, and the standalone `wos-etl-hotspot` agent (see [ETL Hotspot Optimization](#etl-hotspot-optimization-wos-etl-hotspot)).
- **prompts/** — `wos-verify-port.prompt.md`, the Phase 8 verification gate the orchestrator reads and runs inline.
- **skills/** — 11 auto-loading skills (NEON reference, toolchain discovery, SSE/AVX→NEON translation, build-error recipes, WoA dashboard, etc.).
- **references/** — porting-knowledge docs and per-build-system recipes loaded on demand by the agents.
- **etl_hotspot_tool/** — `hotspot_analysis.py`, the Python script the `wos-etl-hotspot` agent runs (SymCache → `wpaexporter` export → source cross-reference).

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

   You should see **wos-porter** listed as enabled. The `/wos-porter:wos-porter` command and the six `wos-*` sub-agents are now available.

To update later, refresh the marketplace and reinstall:

```
/plugin marketplace update extension-wos-porter
/plugin install wos-porter@extension-wos-porter
```

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

### Controlling the work directory (optional)

By default the pipeline clones into `C:\src\wos-porter\<repo>`. Override it by setting `WOS_PORTER_WORKDIR` before launching Claude Code:

```powershell
$env:WOS_PORTER_WORKDIR = "D:\ports"
```

## ETL Hotspot Optimization (`wos-etl-hotspot`)

A **standalone** agent, separate from the porting pipeline. Give it a **project directory** and it runs the full closed loop: **build → profile → optimize → rebuild → re-profile → validate → commit**. It builds the project for ARM64 (with PDBs), obtains a CPU trace, finds the functions that dominate the workload, applies the full range of Windows ARM64 optimizations (**NEON/SVE/SVE2/SME** vectorization plus scalar/branch/memory/compiler tuning) to those hotspots and their in-source callees, then rebuilds and re-profiles to **validate the speedup**, committing each validated win.

**Inputs:**

| Input | Required? | What it is | Example |
|---|---|---|---|
| Project directory | **Always** | Application source root (`.sln`/`.vcxproj`/`CMakeLists.txt`) | `C:\src\sqlite` |
| Workload | Optional | Command to exercise the app during tracing (else auto-detected) | `bench.exe input.dat` |
| ARM64 `.etl` trace | **Only on an x64 host** | A CPU trace captured on a native ARM64 device for this build | `C:\traces\scenario.etl` |

**Host behavior:**

- **ARM64 host** — auto-captures the trace with WPR (needs an elevated shell), re-profiles after optimizing, and reports measured before/after speedups.
- **x64 host** — cross-builds ARM64 binaries but cannot run them, so it **asks for an ARM64-captured `.etl`** and defers post-optimization re-profiling to a native ARM64 rerun (prints the exact commands).

**How to run** — invoke the agent (e.g. the agent picker, or ask the main loop to use it) and provide the project path:

```
Use the wos-etl-hotspot agent to optimize the hotspots in C:\src\sqlite for ARM64.
workload: sqlite3.exe bench.db < queries.sql
```

The agent runs `${CLAUDE_PLUGIN_ROOT}/etl_hotspot_tool/hotspot_analysis.py` (`build` → `capture` → analyze → `compare`), ranks the top 5 source-matched hotspots, optimizes them behind ARM64 guards, validates via re-profiling, and prints a before/after report with commit hashes.

**Additional prerequisites** (beyond those above):

- **Python 3** on PATH (`py -3`, `python`, or `python3`).
- **Windows Performance Toolkit** — `symcachegen.exe`, `wpaexporter.exe`, and (for capture on ARM64) `wpr.exe`, from the Windows ADK / WPT. User-provided; not bundled.
- **Elevation** for WPR capture on an ARM64 host.
- A working **ARM64 build toolchain** (MSVC v143 ARM64 + Windows 11 SDK) so the agent can build the project.

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
- **Marketplace add fails from GitHub** — make sure the plugin files and the root `.claude-plugin/marketplace.json` are committed and pushed to the branch you're pointing at (Claude Code reads the pushed tree, not your local working copy). Pin the branch with `@<branch>` if it isn't on the default branch.
- **Build phase reports missing toolchain** — install the **MSVC v143 - ARM64/ARM64EC build tools** and **Windows 11 SDK** via the Visual Studio Installer, then retry.
