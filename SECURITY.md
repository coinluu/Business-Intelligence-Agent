# Security

## Secrets

API keys are accepted through protected standard input and stored in `.env.local`. On POSIX systems the file is written with mode `0600`. The file, local profile, runtime output, databases, logs, and reports are Git-ignored.

The software can prevent secrets from entering repository files and normal logs. It cannot control retention by the chat product through which a user sends a key. Users with stricter requirements should enter the key locally rather than in chat.

## Source access

This project uses public hotlists and RSS/Atom feeds. It does not bypass authentication, paywalls, rate limits, robots controls, or contractual restrictions. Source-specific credentials must not be stored in `user-profile.yaml`.

## Reporting vulnerabilities

Do not open a public issue containing a real credential, private vault path, collected database, or customer report. Revoke exposed keys immediately and report the issue through the repository owner's private security channel.
