# ARM64 Porter — Windows ARM64 Porting Agent for GitHub Copilot

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
| `arm64-porter` | Main orchestrator — runs the full 7-phase porting pipeline |
| `arm64-analyzer` | Read-only deep scan of a repo for ARM64 readiness |
| `arm64-build-porter` | Modifies build configurations (CMake, MSBuild, Meson, Cargo, etc.) |
| `arm64-code-porter` | Ports x64-specific source code (SIMD, inline asm, arch guards) |
| `arm64-builder` | Builds, validates binaries with dumpbin, and fixes build errors |

## Included Instructions

| File | Purpose |
|------|---------|
| `arm64-build-errors.instructions.md` | Diagnosis and fix patterns for ARM64 compiler/linker errors |
| `arm64-porting-knowledge.instructions.md` | SSE→NEON reference, Windows ARM64 specifics, memory model differences |

## Requirements

- [Visual Studio 2022](https://visualstudio.microsoft.com/) with the **MSVC ARM64 build tools** workload installed
- [GitHub Copilot](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) extension
- VS Code 1.100+

## Usage

1. Install the extension
2. Open Copilot Chat
3. Select the **arm64-porter** agent from the agent picker (or type `@arm64-porter`)
4. Paste a GitHub repository URL:

```
Port https://github.com/user/repo to ARM64
```

The agent will clone the repo, analyze it, port it, build it, and produce a patch — all automatically.

### Other agents

You can also invoke individual agents directly:

- `@arm64-analyzer` — Analyze a local repo path for ARM64 readiness
- `@arm64-builder` — Build and validate an already-ported project

## Commands

| Command | Description |
|---------|-------------|
| `ARM64 Porter: Install Agents` | Install/reinstall all agent and instruction files |
| `ARM64 Porter: Uninstall Agents` | Remove all installed agent and instruction files |
| `ARM64 Porter: Check Installation Status` | Verify which files are installed |

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
