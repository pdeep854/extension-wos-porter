// Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.  
// SPDX-License-Identifier: BSD-3-Clause-Clear

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

const AGENT_FILES = [
    'wos-porter.agent.md',
    'wos-analyzer.agent.md',
    'wos-build-porter.agent.md',
    'wos-code-porter.agent.md',
    'wos-builder.agent.md',
    'wos-tester.agent.md',
    'wos-optimizer.agent.md',
];

function getTargetDir(): string {
    const home = process.env.USERPROFILE || process.env.HOME || '';
    return path.join(home, '.copilot', 'agents');
}

// Sanitize a file name to a bare basename before joining, stripping any
// directory or `..` components so it cannot traverse outside `baseDir`.
function agentPath(baseDir: string, file: string): string {
    return path.join(baseDir, path.basename(file));
}

function copyAgents(context: vscode.ExtensionContext): void {
    const targetDir = getTargetDir();
    if (!fs.existsSync(targetDir)) {
        fs.mkdirSync(targetDir, { recursive: true });
    }
    for (const file of AGENT_FILES) {
        const src = agentPath(path.join(context.extensionPath, 'agents'), file);
        const dst = agentPath(targetDir, file);
        fs.copyFileSync(src, dst);
    }
}

function removeAgents(): void {
    const targetDir = getTargetDir();
    for (const file of AGENT_FILES) {
        const filePath = agentPath(targetDir, file);
        if (fs.existsSync(filePath)) {
            fs.unlinkSync(filePath);
        }
    }
}

async function addToSettings(): Promise<void> {
    const targetDir = getTargetDir();
    const config = vscode.workspace.getConfiguration('chat');
    const locations = { ...(config.get<Record<string, boolean>>('agentFilesLocations') || {}) };
    if (!locations[targetDir]) {
        locations[targetDir] = true;
        await config.update('agentFilesLocations', locations, vscode.ConfigurationTarget.Global);
    }
}

async function removeFromSettings(): Promise<void> {
    const targetDir = getTargetDir();
    const config = vscode.workspace.getConfiguration('chat');
    const locations = { ...(config.get<Record<string, boolean>>('agentFilesLocations') || {}) };
    if (locations[targetDir] !== undefined) {
        delete locations[targetDir];
        await config.update(
            'agentFilesLocations',
            Object.keys(locations).length > 0 ? locations : undefined,
            vscode.ConfigurationTarget.Global
        );
    }
}

export function activate(context: vscode.ExtensionContext) {
    // On every activation: copy agents and register path
    try {
        copyAgents(context);
        addToSettings();
    } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`WoS Porter: ${msg}`);
    }

    // Command: Reinstall agents
    context.subscriptions.push(
        vscode.commands.registerCommand('wosPorter.install', async () => {
            try {
                copyAgents(context);
                await addToSettings();
                const selection = await vscode.window.showInformationMessage(
                    `WoS Porter: Agents installed to ${getTargetDir()}`,
                    'Reload Window'
                );
                if (selection === 'Reload Window') {
                    vscode.commands.executeCommand('workbench.action.reloadWindow');
                }
            } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : String(err);
                vscode.window.showErrorMessage(`WoS Porter: ${msg}`);
            }
        })
    );

    // Command: Uninstall agents and clean settings
    context.subscriptions.push(
        vscode.commands.registerCommand('wosPorter.uninstall', async () => {
            const confirm = await vscode.window.showWarningMessage(
                'Remove all WoS Porter agents and settings entry?',
                { modal: true },
                'Remove'
            );
            if (confirm !== 'Remove') { return; }

            removeAgents();
            await removeFromSettings();

            vscode.window.showInformationMessage(
                'WoS Porter: Agents removed and settings cleaned.',
                'Reload Window'
            ).then(selection => {
                if (selection === 'Reload Window') {
                    vscode.commands.executeCommand('workbench.action.reloadWindow');
                }
            });
        })
    );

    // Command: Status
    context.subscriptions.push(
        vscode.commands.registerCommand('wosPorter.status', () => {
            const targetDir = getTargetDir();
            const installed = AGENT_FILES.filter(f => fs.existsSync(agentPath(targetDir, f)));
            vscode.window.showInformationMessage(
                `WoS Porter: ${installed.length}/${AGENT_FILES.length} agents in ${targetDir}`,
                { modal: true }
            );
        })
    );
}

export function deactivate() {}
