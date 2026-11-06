#!/usr/bin/env bash
# A readable, read-only service overview with an explicit one-service restart.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$root/scripts/lab-recover.py" "$@"
