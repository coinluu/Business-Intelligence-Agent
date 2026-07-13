# Installation

The recommended installation path is to give the repository URL to an Agent and require it to follow `AGENTS.md`.

## Manual bootstrap

```bash
git clone <repository-url>
cd Business-Intelligence-Agent
./scripts/bootstrap.sh
cp user-profile.example.yaml user-profile.yaml
```

On Windows, replace the bootstrap command with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Edit `user-profile.yaml`, then apply it:

```bash
uv run bia configure --profile-file user-profile.yaml
uv run bia init --api-key-stdin
```

If no single Obsidian vault was detected:

```bash
uv run bia set-vault "/absolute/path/to/Vault"
```

Validate and run:

```bash
uv run bia doctor --live-api
uv run bia run
uv run bia schedule install
uv run bia schedule status
```

`bia run` is intentionally a real run. Depending on the selected sources and model, it can take time and consume API tokens.

## Platform scheduling

- macOS installs `~/Library/LaunchAgents/io.github.business-intelligence-agent.plist`.
- Linux installs a systemd user service and timer under `~/.config/systemd/user`.
- Windows creates the `io.github.business-intelligence-agent` Task Scheduler task.

The operating-system scheduler wakes every five minutes. The product reads `user-profile.yaml` and decides whether collection or a report is due, so later timing changes do not require hand-editing task definitions.

## Uninstall

```bash
uv run bia schedule uninstall
```

This removes only the scheduler. The repository, local configuration, collected databases, and Obsidian reports remain until the user explicitly deletes them.
