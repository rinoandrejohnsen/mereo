#!/usr/bin/env bash
# Suite 6 -- being a good Linux citizen, observed from outside the process.
# See drive.py; the pty and fork control it needs are why this suite is Python.
#
#   ./tests/citizen/run.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
exec python3 "$DIR/drive.py"
