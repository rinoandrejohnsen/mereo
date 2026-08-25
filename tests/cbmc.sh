#!/usr/bin/env bash
# Suite 7 -- BOUNDED MODEL CHECKING of the generated C, with CBMC.
#
# A second opinion that is not another abstract interpretation. CBMC is
# bit-precise and answers with a COUNTEREXAMPLE, so where mereoc says "not
# proved" this says either "here is the input" or nothing at all. It found two
# real bugs the day it was installed -- a guard whose subject overflowed a
# signed long, and `count + length <= limit` wrapping unsigned -- each of which
# had taken a morning to find by hand.
#
# Every program mereoc ACCEPTS must verify. The exceptions are listed, with a
# reason, and a listed program that starts verifying is a failure too: that is
# the whole point of writing them down.
#
#   ./tests/cbmc.sh
set -u
DIR=$(cd "$(dirname "$0")/.." && pwd)
B=${TMPDIR:-/tmp}/mereo-cbmc.$$
mkdir -p "$B"
trap 'rm -rf "$B"' EXIT

UNWIND=${UNWIND:-6}
TIMEOUT=${TIMEOUT:-90}

# Known open, each confirmed by CBMC and each already reported by mereoc as
# unproved rather than refused. Fixing one means removing it from here.
declare -A EXPECT_FAIL=(
)
# Not a hole -- a cost. 19 buffers needs --object-bits 14, and then it is four
# and a half minutes for one program. Run it by hand:
#   cbmc --function _start --unwind 6 --object-bits 14 linux_calls.c
declare -A SKIP=( [linux_calls]="needs --object-bits 14; 272s" )

pass=0 fail=0 refused=0 skipped=0
for src in "$DIR"/tests/progs/*.mereo; do
    name=$(basename "$src" .mereo)
    if [ -n "${SKIP[$name]:-}" ]; then
        printf '  %-30s skip  (%s)\n' "$name" "${SKIP[$name]}"
        skipped=$((skipped+1)); continue
    fi
    if ! timeout 90 python3 "$DIR/mereoc.py" "$src" > "$B/$name.c" 2>/dev/null; then
        refused=$((refused+1)); continue      # a planted violation; never built
    fi
    python3 "$DIR/tools/tocbmc.py" "$B/$name.c" "$B/$name.cbmc.c" 2>/dev/null
    timeout "$TIMEOUT" cbmc --function _start --unwind "$UNWIND" \
            --no-unwinding-assertions "$B/$name.cbmc.c" > "$B/$name.out" 2>&1
    rc=$?
    want_fail=${EXPECT_FAIL[$name]:+1}
    case "$rc:${want_fail:-0}" in
        0:0)  pass=$((pass+1)) ;;
        10:1) printf '  %-30s open, as recorded  (%s)\n' "$name" "${EXPECT_FAIL[$name]}"
              pass=$((pass+1)) ;;
        0:1)  printf '  %-30s NOW VERIFIES -- drop it from EXPECT_FAIL\n' "$name"
              fail=$((fail+1)) ;;
        10:0) printf '  %-30s FAILED\n' "$name"
              grep ': FAILURE' "$B/$name.out" | sed -E 's/^\[[a-z_.0-9]+\] //' \
                  | cut -c1-88 | head -3 | sed 's/^/      /'
              fail=$((fail+1)) ;;
        124:*) printf '  %-30s TIMEOUT after %ss\n' "$name" "$TIMEOUT"; fail=$((fail+1)) ;;
        *)    printf '  %-30s cbmc exit %s\n' "$name" "$rc"
              tail -1 "$B/$name.out" | sed 's/^/      /'; fail=$((fail+1)) ;;
    esac
done
printf 'cbmc: %d ok, %d fail  (%d refused by mereoc, %d skipped)\n' \
       "$pass" "$fail" "$refused" "$skipped"
[ "$fail" = 0 ]
