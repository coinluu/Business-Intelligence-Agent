# Agent operating contract

These instructions are mandatory for any Agent installing or maintaining this repository.

## Non-negotiable outcome

Convert the user's information objective into a tested local workflow that collects relevant public data, generates the requested Markdown, writes it to the correct Obsidian vault, and runs on the requested schedule. Never claim completion based only on dependency installation or a zero exit code.

## First-install protocol

### 1. Inspect before asking

If `uv` is missing, run `./scripts/bootstrap.sh` on macOS/Linux or `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1` on Windows. Otherwise run, in order:

```bash
uv sync --frozen
uv run bia detect
```

Detect the OS, architecture, Python/uv state, network and proxy hints, timezone, scheduler availability, and registered Obsidian vaults. Do not ask the user for facts that can be detected safely.

### 2. Ask only for required intent

Collect these four inputs in natural language:

1. **Information target:** topics, companies, industries, regions, languages, important event types, requested/excluded sources, and exclusions. Accept an incomplete natural-language description and translate it into a concrete profile.
2. **Markdown outcome:** required sections, depth, language, filename/folder preference, source links, frontmatter, and any example. If unspecified, propose a small default structure and ask for one confirmation.
3. **Timing:** collection frequency and report time(s). Use the detected system timezone unless the user requests another.
4. **Model connection:** API key, model, and base URL when non-standard. The user may send the key in chat.

Conditional questions are allowed only when automatic resolution is unsafe, including multiple/no Obsidian vaults, login-only sources, paid services, overwrite risk, or an unrecognized model endpoint.

Never ask the user to identify their OS, Python version, Git installation, timezone, routine network state, or a single unambiguous registered vault.

### 3. Apply configuration safely

1. Copy `user-profile.example.yaml` to a temporary file outside the repository's tracked files.
2. Translate the user's answers into that schema; `schemas/user-profile.schema.json` is the machine-readable contract. Do not invent credentials, sources, or business requirements.
3. Set each `onboarding.*_confirmed` value to `true` only after the user answered that category or explicitly accepted the proposed default. The example intentionally cannot be installed unchanged.
4. Run `uv run bia configure --profile-file <temporary-file>`.
5. Supply the API key with `uv run bia init --api-key-stdin` or `uv run bia configure --profile-file <file> --api-key-stdin`. Do not place a literal key in a command argument.
6. If exactly one vault was detected, initialization may select it automatically. Otherwise use `uv run bia set-vault <path>` after user selection.
7. Never edit `runtime/` directly.

The API key may be received in chat. Once received, write it only to `.env.local`, keep permissions restricted where supported, never repeat the full value, and never include it in logs, Git, reports, task definitions, or final replies.

### 4. Validate with real evidence

Run:

```bash
uv run bia validate
uv run bia doctor --live-api
uv run bia run
```

Confirm all of the following:

- source databases exist and are non-empty;
- the report file is non-empty and lies inside the intended vault/folder;
- the report contains the configured title/sections and source references;
- the file can be read back after its atomic write;
- no API key appears in tracked or generated text;
- failed sources are reported, not omitted silently.

Then install the scheduler and force/await one real scheduled execution:

```bash
uv run bia schedule install
uv run bia schedule status
```

Do not mark a platform as verified unless it was exercised on that operating system.

## Later natural-language changes

When the user asks to add/remove topics or sources, change report content, move the Obsidian folder, or change timing:

1. Read the current `user-profile.yaml`; do not restart onboarding.
2. Map only the requested change into a temporary complete profile.
3. Show a concise change summary when the effect is material.
4. Apply it with `bia configure`; this creates a backup and validates generated configuration.
5. Run `bia doctor`; then run a live report test when input, model, source, report, or delivery behavior changed.
6. Reinstall the scheduler only when scheduling or installation paths changed.
7. If validation or testing fails, restore the backup and report the exact failure.

Examples:

- “Add robotics and embodied AI” changes targets/keywords, then requires a live source/report test.
- “Remove funding news” changes exclusions, then requires a live report test.
- “Run at 09:30” changes `schedule.report_times`; validate and let the five-minute scheduler tick use the new profile.
- “Pause updates” runs `uv run bia schedule pause`; it does not alter the profile.

## Scope and truthfulness

- Do not add notification, cloud hosting, paid storage, or public deployment unless requested.
- Do not bypass authentication, paywalls, anti-bot controls, or source terms.
- Ask for credentials only when the chosen source requires them.
- Keep unrelated upstream code unchanged.
- Report `DEGRADED` when some sources fail and `FAILED` when the requested output cannot be verified.
- Never call a sample profile, dry run, mocked test, or registered task a successful production installation.

## Completion response

Report:

- configured information objective;
- active sources and any failed/unresolved sources;
- model connection status without the key;
- exact Obsidian report path;
- collection/report timing and timezone;
- live run counts and report validation;
- scheduler status and platform actually verified;
- remaining limitations, or `None`.
