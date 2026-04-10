# Contributing to Hermes Dashboard

Thanks for helping build Hermes Dashboard.

## Before You Start

- make sure you can run the dashboard locally
- read the main [README](README.md) for install and runtime details
- check open issues before starting new work

## Development Setup

1. Clone the repo.
2. Make sure you have access to a working Hermes install.
3. Start the API and dashboard locally.
4. Confirm the app loads and the area you want to change is reproducible.

Typical local workflow:

```sh
./run-api-server.sh
./run-dashboard.sh
```

## How to Contribute

1. Open an issue, or comment on an existing one, so work is visible.
2. Create a branch for your change.
3. Keep changes focused and small when possible.
4. Test the behavior you changed locally.
5. Update docs when user-facing behavior changes.
6. Commit with a clear message that explains the change.
7. Open a pull request with a short summary, why it is needed, and how it was tested.

## What to Include in a Pull Request

- what changed
- why it changed
- screenshots for UI changes when helpful
- manual test steps or commands used
- linked issue, if there is one

## Contribution Guidelines

- prefer minimal fixes over large rewrites
- keep the standalone dashboard compatible with upstream Hermes installs
- do not commit secrets, local `.env` files, runtime PID files, or machine-specific paths
- if you change setup, behavior, or workflows, update the README or related docs

## Reporting Bugs

When filing a bug, include:

- what you expected
- what happened instead
- steps to reproduce
- environment details
- logs or screenshots if available

## Questions

If you are unsure about an approach, open an issue first so we can align before you spend time on a larger change.
