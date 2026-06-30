// Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
// SPDX-License-Identifier: BSD-3-Clause-Clear

// Runs via the package.json "vscode:uninstall" lifecycle hook when the
// extension is fully uninstalled. It executes as a plain Node process with
// NO access to the `vscode` API, so cleanup uses fs/path only. This mirrors
// getTargetDir() + AGENT_FILES in src/extension.ts — keep the list in sync.

const fs = require('fs');
const path = require('path');

const AGENT_FILES = [
    'wos-porter.agent.md',
    'wos-analyzer.agent.md',
    'wos-build-porter.agent.md',
    'wos-code-porter.agent.md',
    'wos-builder.agent.md',
    'wos-tester.agent.md',
    'wos-optimizer.agent.md',
];

function getTargetDir() {
    const home = process.env.USERPROFILE || process.env.HOME || '';
    return path.join(home, '.copilot', 'agents');
}

// Sanitize to a bare basename before joining (mirrors agentPath in extension.ts).
function agentPath(baseDir, file) {
    return path.join(baseDir, path.basename(file));
}

try {
    const targetDir = getTargetDir();

    for (const file of AGENT_FILES) {
        const filePath = agentPath(targetDir, file);
        try {
            if (fs.existsSync(filePath)) {
                fs.unlinkSync(filePath);
            }
        } catch (err) {
            // Best-effort: keep removing the rest even if one file fails.
            console.error(`WoS Porter uninstall: failed to remove ${filePath}: ${err.message}`);
        }
    }

    // Remove the agents directory only if our cleanup left it empty, so we
    // don't delete agents owned by other tools/extensions.
    try {
        if (fs.existsSync(targetDir) && fs.readdirSync(targetDir).length === 0) {
            fs.rmdirSync(targetDir);
        }
    } catch {
        // Non-fatal — leave the directory in place.
    }
} catch (err) {
    console.error(`WoS Porter uninstall: ${err && err.message ? err.message : err}`);
}
