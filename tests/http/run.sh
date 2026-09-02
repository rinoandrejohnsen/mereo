#!/usr/bin/env bash
# Suite 7 -- the HTTP request parser, differentially.
#
# The parser is exercised as a BLACK BOX: `probe` reads a request on stdin and
# prints the parse in hex, and drive.py compares that against an oracle written
# from the same rules. The half that matters most is truncation -- every proper
# prefix of a valid request must come back -2, because a parser that says -1 on
# a short read makes a server drop requests that were merely still arriving.
#
#   ./tests/http/run.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
ROOT=$(cd "$DIR/../.." && pwd)
OUT=${OUT:-$ROOT/build}
PROBE="$OUT/probe"
PROBE_RESPONSE="$OUT/probe_response"
PROBE_CHUNKED="$OUT/probe_chunked"
PROBE_JSON="$OUT/probe_json"
for p in "$PROBE" "$PROBE_RESPONSE" "$PROBE_CHUNKED" "$PROBE_JSON"; do
    if [ ! -x "$p" ]; then
        echo "  http parser: $p is missing -- run ./build.sh first"
        exit 1
    fi
done
exec python3 "$DIR/drive.py" "$PROBE" "$PROBE_RESPONSE" "$PROBE_CHUNKED" "$PROBE_JSON"
