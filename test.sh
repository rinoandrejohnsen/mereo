#!/usr/bin/env bash
# The full test run -- three suites plus the build gate.
#
#   1. UNIT tests for RAII + error handling  (tests/scopes/run.sh)
#      Small mereo programs paired with equivalent C++; strace both and assert
#      the resource RELEASE ORDER is identical, on normal AND fault paths.
#      Tests the mechanism (destruction/tower) against C++ as the oracle.
#
#   2. BLACK-BOX tests of the binaries       (tests/blackbox.sh)
#      Each shipped program run as an opaque box: stdin/args -> stdout + exit;
#      plus mereoraii (strace + fault injection) asserting on the real binary
#      that fds are freed and error records are correct on every fault path.
#
#   3. mereo VERSUS C                        (tests/versus/run.sh)
#      Tiny paired programs -- one mereo, one hand-written freestanding C doing
#      the same job with the same checks -- compared on the instruction
#      histogram and .text size. Suites 1 and 2 ask whether mereo is CORRECT;
#      this one asks what its abstractions COST, against C as the oracle.
#
# Also runs build.sh (mereocheck hot/cold layout gate) and checks every declared
# syscall number against <asm/unistd_64.h>.
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
rc=0

echo "### Suite 1 -- RAII + error-handling unit tests"
"$DIR/tests/scopes/run.sh"   || rc=1
echo
echo "### Suite 2 -- black-box binary tests"
"$DIR/tests/blackbox.sh" || rc=1
echo
echo "### Suite 3 -- mereo versus C, on the generated code"
"$DIR/tests/versus/run.sh" || rc=1
echo
echo "### Build + layout gate"
"$DIR/build.sh" >/dev/null 2>&1 && echo "  build + mereocheck: ok" \
    || { echo "  build FAIL"; rc=1; }
# ...and one program from tests/progs, named explicitly: a NESTED crossroad (a
# crossroad inside a cold road) is a layout claim like any other, and the only
# program that makes it lives with the black-box programs, which the gate's
# default sweep does not walk.
"$DIR/build.sh" tests/progs/tmpl_road_nest.mereo >/dev/null 2>&1 \
    && echo "  nested crossroad layout: ok" \
    || { echo "  nested crossroad layout FAIL"; rc=1; }
# A wrong syscall NUMBER is the one mistake in linux.mereo that reading does not
# catch: the neighbouring call usually exists and fails like something else.
python3 "$DIR/tools/check_syscalls.py" "$DIR/linux.mereo" || rc=1
# A highlighter fails QUIETLY -- an unknown construct is still printed, just
# unstyled. This is the mechanical version of noticing.
python3 "$DIR/tools/check_highlight.py" "$DIR" || rc=1
# The library's worked examples live in COMMENTS, so no compiler reads them. The
# syntax change left twenty-odd of them spelled in a surface that no longer
# parses -- and they are exactly what a reader copies.
python3 "$DIR/tools/check_comments.py" "$DIR" || rc=1

echo
[ $rc = 0 ] && echo "ALL GREEN" || echo "FAILURES"
exit $rc
