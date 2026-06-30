# WoS Porter — Windows ARM64 Porting Agent for GitHub Copilot

AI-powered agents that automatically port open-source x64 Windows applications to native ARM64.

## What It Does

Give it a GitHub repository URL and it will:

1. **Analyze** the repo for x64-specific code (SIMD intrinsics, inline assembly, architecture guards)
2. **Port the build system** — adds ARM64 targets to CMake, MSBuild, Meson, Cargo, Make, and 15+ other build systems
3. **Port source code** — translates SSE/AVX intrinsics to NEON, adds ARM64 preprocessor guards, fixes calling conventions
4. **Build** the project for ARM64 using MSVC, iteratively fixing compilation errors
5. **Validate** every output binary with `dumpbin` to confirm ARM64 architecture
6. **Run tests** on ARM64 hardware (when available)
7. **Generate a report** with a ready-to-apply git patch

## Included Agents

| Agent | Role |
|-------|------|
| `wos-porter` | Main orchestrator — runs the full 8-phase porting pipeline |
| `wos-analyzer` | Read-only deep scan of a repo for ARM64 readiness |
| `wos-build-porter` | Modifies build configurations (CMake, MSBuild, Meson, Cargo, etc.) |
| `wos-code-porter` | Ports x64-specific source code (SIMD, inline asm, arch guards) |
| `wos-builder` | Builds, validates binaries with dumpbin, and fixes build errors |
| `wos-tester` | Runs and fixes ARM64 test suites and benchmarks |
| `wos-optimizer` | Applies hand-written ARM NEON intrinsics to hot kernels for performance |

## Included Instructions

| File | Purpose |
|------|---------|
| `wos-build-errors.instructions.md` | Diagnosis and fix patterns for ARM64 compiler/linker errors |
| `wos-porting-knowledge.instructions.md` | SSE→NEON reference, Windows ARM64 specifics, memory model differences |

## Requirements

- [Visual Studio 2022](https://visualstudio.microsoft.com/) with the **MSVC ARM64 build tools** workload installed
- [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension
- VS Code 1.100+

## Installation

### From VSIX File

1. **Package the extension** (if you haven't already):
   ```
   npm run package
   ```
   This produces a `.vsix` file in the project root.

2. **Install in VS Code** using one of these methods:

   **Option A — VS Code UI:**
   - Open VS Code
   - Go to the Extensions view (`Ctrl+Shift+X`)
   - Click the `...` menu (top-right of the Extensions panel)
   - Select **"Install from VSIX..."**
   - Browse to and select the `.vsix` file

   **Option B — Command Palette:**
   - Open the Command Palette (`Ctrl+Shift+P`)
   - Type **"Extensions: Install from VSIX"**
   - Browse to and select the `.vsix` file

   **Option C — Command Line:**
   ```
   code --install-extension wos-porter-<version>.vsix
   ```

3. **Reload VS Code** when prompted.

## Usage

1. Install the extension (see [Installation](#installation) above)
2. Open Copilot Chat
3. Select the **wos-porter** agent from the agent picker
4. Paste a GitHub repository URL:

```
Port https://github.com/user/repo to ARM64
```

The agent will clone the repo, analyze it, port it, build it, and produce a patch — all automatically.

### Other agents

You can also invoke individual agents directly:

- `wos-builder` — Build and validate an already-ported project
- `wos-tester` — Run and fix ARM64 test suites and benchmarks
- `wos-optimizer` — Apply ARM NEON intrinsics to hot kernels

## Using the Agents in Claude Code

In [Claude Code](https://docs.claude.com/en/docs/claude-code) the recommended setup is a **single `/wos-porter` slash command** as the entry point. It hands the job to the `wos-porter` agent, which then delegates each phase to the other six agents (analyzer, build-porter, code-porter, builder, tester, optimizer) — exactly the same orchestration the extension uses. You run one command; the sub-agents are invoked for you.

This uses two Claude Code directories:

- `.claude/commands/` — the one user-facing slash command (`/wos-porter`)
- `.claude/agents/` — the seven agents the command and orchestrator use as subagents

Use `~/.claude/...` instead of `.claude/...` for either to make them available in every project.

### 1. Install the seven agents as subagents

Copy all seven agent files into `.claude/agents/`, renaming `*.agent.md` → `*.md` (Claude Code's subagent name is the filename minus `.md`). They ship under `agents/` in the extension and install to `~/.copilot/agents/`:

```bash
mkdir -p .claude/agents
for f in ~/.copilot/agents/wos-*.agent.md; do
  name=$(basename "$f" .agent.md)
  cp "$f" ".claude/agents/$name.md"
done
```

In each copied file, convert the Copilot frontmatter to Claude Code subagent frontmatter:

| Copilot key | Claude Code subagent key |
|---|---|
| `tools: [execute, read, edit, search, todo, agent]` | `tools: Bash, Read, Edit, Write, Grep, Glob, TodoWrite, Task` |
| `description`, `name` | keep as-is (both used by subagents) |
| `argument-hint`, `user-invocable`, `agents` | remove (not used by subagents) |

Tool-name mapping: `execute`→`Bash`, `read`→`Read`, `edit`→`Edit`/`Write`, `search`→`Grep`/`Glob`, `todo`→`TodoWrite`, `agent`→`Task`. Omit the `tools` line entirely to grant all tools — the simplest option. **`wos-porter` must keep the `Task` tool** so it can invoke the other six subagents.

### 2. Create the single `/wos-porter` slash command

Add one file, `.claude/commands/wos-porter.md`, that delegates to the `wos-porter` agent and passes the repo URL through with `$ARGUMENTS`:

```markdown
---
description: Port an open-source x64 application to Windows ARM64.
argument-hint: <github-repo-url>
allowed-tools: Task
---

Use the **wos-porter** subagent to port the following repository to native
Windows ARM64. It must run its full pipeline — analyze, port the build system
and source, build, validate with dumpbin, test, and optimize — delegating each
phase to the wos-analyzer, wos-build-porter, wos-code-porter, wos-builder,
wos-tester, and wos-optimizer subagents as defined in its instructions.

Repository: $ARGUMENTS
```

The slash command itself stays tiny — all the porting logic lives in the `wos-porter` agent body, unchanged.

### 3. Run it

Type `/` to confirm `/wos-porter` is listed, then invoke it with a repo URL:

```
> /wos-porter https://github.com/user/repo
```

Claude Code launches the `wos-porter` agent, which in turn spawns the analyzer, porters, builder, tester, and optimizer subagents to complete the port. Run `/agents` to verify all seven subagents loaded.

## Commands

| Command | Description |
|---------|-------------|
| `WoS Porter: Install Agents` | Install/reinstall all agent and instruction files |
| `WoS Porter: Uninstall Agents` | Remove all installed agent and instruction files |
| `WoS Porter: Check Installation Status` | Verify which files are installed |

## Supported Build Systems

CMake, MSBuild/Visual Studio, Meson, Make/NMake, Cargo (Rust), Autotools, Bazel, GN, Premake, SCons, Waf, qmake, xmake, B2/Boost.Build, Go, node-gyp, .NET SDK, Gradle, Python C extensions.

## License

Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.  
SPDX-License-Identifier: BSD-3-Clause-Clear

## Build Commands

All build and development commands should be run from the project root directory.

### Install Dependencies

```
npm install
```

### Compile TypeScript

```
npm run compile
```

### Watch for Changes (Auto-compile)

```
npm run watch
```

### Package Extension (VSIX)

```
npm run package
```

### Publish Extension

```
npm run publish
```

### Uninstall Agents

```
npm run vscode:uninstall
```

### Clean Build Artifacts

To clean build files manually, remove the following:
- `out/` directory
- Any `*.js`, `*.js.map`, `*.tsbuildinfo` files
- `node_modules/.cache` (if present)

---
