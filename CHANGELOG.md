# Changelog

## 1.0.1

- Fix: agent files are now removed from `~/.copilot/agents/` on extension uninstall (added the missing `uninstall.js` referenced by the `vscode:uninstall` hook)
- Add `wos-tester` and `wos-optimizer` agents to the install/uninstall set (now 7 agents total)
- Harden agent file path handling against path traversal
- README: document using the agents in Claude Code via a `/wos-porter` slash command

## 1.0.0

- Initial release
- 5 custom Copilot agents for ARM64 porting workflow
- 2 instruction files with ARM64 build error and porting knowledge references
- Auto-install on first activation
- Commands: Install, Uninstall, Check Status
