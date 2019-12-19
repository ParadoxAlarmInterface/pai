#!/usr/bin/env sh
set -e

cd "${0%/*}"
python3 -m paradox.console_scripts.pai_run "$@"
