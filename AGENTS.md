# Agent guide

## Development

- Use Python 3.11+ in `.venv` at the repository root (one per worktree). If it is missing, create it: `python3 -m venv .venv && .venv/bin/python -m pip install -e . pytest pytest-asyncio pytest-mock pyyaml`. Run tools through `.venv/bin/python`.
- Run focused tests from the repository root, for example `python -m pytest -q tests/hardware/digiplex`; run the full suite with `python -m pytest -q`. CI's lint configuration is in `.github/workflows/test.yml` and `.flake8`; tox configuration is in `pyproject.toml`.

## Panel changes

- Keep transport code in `paradox/connections/` and panel-family behavior in its `paradox/hardware/` driver, not in the generic coordinator or base panel. Prefix family-only configuration with the family name, such as `DIGIPLEX_`.
- Discovery may fall back to another protocol only when the initial probe is unanswered; startup and login failures must not trigger fallback.
- For connection changes, run `tests/paradox/test_connect_sequence.py` and the relevant family tests. Scripted transports do not verify physical-panel compatibility or timing.

## Pull requests

- Target `dev`; pull requests are squash-merged.
