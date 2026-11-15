# Agent guide

## Development

- Use Python 3.10+ and a virtual environment. If dependencies are missing, install them with `python -m pip install -e . pytest pytest-asyncio pytest-mock pyyaml`.
- Run focused tests from the repository root, for example `python -m pytest -q tests/hardware/digiplex`; run the full suite with `python -m pytest -q`. CI's lint and tox configuration is in `.github/workflows/test.yml` and `tox.ini`.

## Panel changes

- Keep transport code in `paradox/connections/` and panel-family behavior in its `paradox/hardware/` driver, not in the generic coordinator or base panel. Prefix family-only configuration with the family name, such as `DIGIPLEX_`.
- Discovery may fall back to another protocol only when the initial probe is unanswered; startup and login failures must not trigger fallback.
- For connection changes, run `tests/paradox/test_connect_sequence.py` and the relevant family tests. Scripted transports do not verify physical-panel compatibility or timing.
