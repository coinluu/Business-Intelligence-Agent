# Agent-managed operations

Users can describe changes in natural language. The Agent edits the complete profile through the validated `bia configure` path, never generated runtime files.

## Common operations

```bash
uv run bia status
uv run bia doctor
uv run bia run
uv run bia schedule pause
uv run bia schedule resume
```

## Safe reconfiguration

1. Read `user-profile.yaml`.
2. Produce a complete temporary YAML with only the requested semantic change.
3. Apply it: `uv run bia configure --profile-file <temporary-file>`.
4. Inspect the backup path returned by the command.
5. Run `uv run bia doctor`.
6. Run `uv run bia run` when the change affects sources, filtering, model behavior, report rendering, or delivery.

The system compiles `runtime/config.yaml`, `runtime/frequency_words.txt`, and `runtime/profile.yaml` atomically. Manual changes in `runtime/` are overwritten.

## Recovery

Validated profile backups are stored under `.backups/`. If a live test fails after a valid configuration change, copy the most recent known-good profile to a temporary path and apply it through `bia configure` again. Do not restore `.env.local` from chat or logs.
