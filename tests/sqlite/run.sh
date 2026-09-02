#!/usr/bin/env bash
# Suite 8 -- the SQLite file-format reader, against databases the real sqlite3
# wrote. The fixtures are not hand-rolled, so the bytes under test are the
# bytes SQLite actually produces; the oracle re-reads the header from the
# published format and the mereo probe is compared against it.
#
#   ./tests/sqlite/run.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
OUT=${OUT:-$ROOT/build}
PROBE="$OUT/probe_open"
if [ ! -x "$PROBE" ]; then
    echo "  sqlite header: $PROBE is missing -- run ./build.sh first"
    exit 1
fi
exec python3 "$DIR/drive.py" "$PROBE"
