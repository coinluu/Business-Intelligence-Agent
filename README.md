# Business Intelligence Agent

An Agent-installable system that collects public business information, evaluates it with the user's model, writes structured Markdown into Obsidian, and keeps the workflow running on a schedule.

This repository includes the proven TrendRadar collection engine plus a separate macOS product layer for environment detection, minimal-question onboarding, safe configuration, LaunchAgent scheduling, verification, and later Agent-managed changes.

## Give this repository to an Agent

Send the repository URL to a coding Agent and say:

> Install this business intelligence system for me. Follow AGENTS.md, ask only for information that cannot be detected, run a real end-to-end test, and do not claim success until the Markdown file is verified in my Obsidian vault.

The Agent must read [AGENTS.md](AGENTS.md) before changing the machine.

A bootstrap command is included for Macs without `uv`: `scripts/bootstrap.sh`.

## What the installer asks

Only four inputs are normally required:

1. What information should be monitored?
2. What should the Markdown report contain and look like?
3. When and how often should it update?
4. Which model/API should be used? The API key may be supplied in chat.

The installer detects the operating system, dependencies, network/proxy hints, timezone, scheduler, and registered Obsidian vaults. It asks about a vault only when none or more than one can be resolved safely.

## Product commands

```bash
uv sync --frozen
uv run bia detect
uv run bia init
uv run bia configure --profile-file /path/to/profile.yaml
uv run bia set-vault /path/to/ObsidianVault
uv run bia doctor --live-api
uv run bia test
uv run bia run
uv run bia schedule install
uv run bia status
uv run bia update
```

Scheduler management:

```bash
uv run bia schedule status
uv run bia schedule pause
uv run bia schedule resume
uv run bia schedule uninstall
```

## Supported system

- macOS 13 or later: LaunchAgent
- Python 3.12+
- Local Obsidian vaults already initialized by Obsidian

Public hotlists and RSS/Atom feeds are supported directly. Login-only, paid, anti-bot, or contract-restricted sources require a source-specific integration and credentials; the system reports these as unresolved instead of pretending they were collected.

## Configuration model

- `user-profile.yaml`: the single editable source of truth for monitoring goals, sources, report structure, delivery, and timing. It is local and Git-ignored.
- `.env.local`: API key, resolved vault path, and optional proxy values. It is local, permission-restricted, and Git-ignored.
- `runtime/`: generated configuration. Never edit it manually.
- `.state/`: scheduler and run state. Never commit it.

Start from [user-profile.example.yaml](user-profile.example.yaml). See [INSTALL.md](INSTALL.md) for manual installation and [OPERATIONS.md](OPERATIONS.md) for later changes.
The machine-readable profile contract is [schemas/user-profile.schema.json](schemas/user-profile.schema.json).
The example has three onboarding confirmations set to `false`; validation refuses to install it unchanged. An Agent may set them to `true` only after the user answers or accepts the corresponding proposed default.

## Success definition

Installation is complete only when:

- profile validation and environment checks pass;
- a live model request succeeds;
- real sources are collected;
- a non-empty Markdown report is atomically written into the selected vault;
- the written file is read back successfully;
- the operating-system scheduler completes a real run;
- secrets, databases, logs, and reports are absent from Git.

Partial source failure is reported as degraded coverage, never as full success.

## Security and provenance

See [SECURITY.md](SECURITY.md) and [UPSTREAM.md](UPSTREAM.md). The underlying collection engine is derived from TrendRadar and the full repository is distributed under GPL-3.0. This product does not bypass authentication, paywalls, robots controls, or source terms. Non-macOS installation is rejected explicitly.
