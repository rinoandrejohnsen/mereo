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
#   4. namespaces VERSUS C++                 (tests/namespaces/run.sh)
#      The same nine questions asked of a mereo namespace and a C++ one, in two
#      programs that must print the same nine numbers. Suite 3 asks what an
#      abstraction costs; this asks whether one MEANS what its name claims.
#
#   5. CHECKING versus C++ and Zig           (tests/checking/run.sh)
#      One mistake written three times and compiled by each: is it refused, and
#      does the error point at the line it is on? The second half is the whole
#      argument about `concept` and about deriving a port's requirement.
#
#   6. WHERE THE BYTES ARE                   (tests/size/run.sh)
#      mereo is bigger than its hand-written C twin, and the reason given for
#      years was that the extra is cold -- error blocks and the release tower.
#      This attributes every byte and checks that the answer is still whatever
#      the docs claim, since the figures drifted once already while nobody was
#      measuring.
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
# The claim that a mereo namespace IS a namespace in C++'s sense is checked the
# only way a claim like that can be: the same program written twice, compared on
# what it prints.
echo "### Suite 4 -- mereo namespaces versus C++ namespaces"
"$DIR/tests/namespaces/run.sh" || rc=1

echo
# What the compiler CATCHES, against two languages that answer the same question
# differently. Zig is optional -- its column is skipped when it is not installed.
echo "### Suite 5 -- compile-time checking versus C++ and Zig"
"$DIR/tests/checking/run.sh" || rc=1

echo
# Where the extra bytes are, attributed rather than asserted.
echo "### Suite 6 -- where mereo's bytes are, against the C twin"
"$DIR/tests/size/run.sh" || rc=1
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
# A KNOWN ANSWER, because the corpus had none and paid for it. `x25519` runs the
# Montgomery ladder over RFC 7748 s5.2 and prints the shared secret, so it is a
# whole crypto primitive checked against a number someone else published. It
# earned its place: a stack-slot change once moved this result and left every
# other suite green, because nothing here executed the TLS stack at all. A
# transform that rearranges storage cannot be trusted to a build gate.
X25519_RFC7748=c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552
if python3 "$DIR/mereoc.py" "$DIR/programs/tls/x25519.mereo" > "$DIR/.x25519.c" 2>/dev/null \
   && gcc -O2 -fwrapv -nostdlib -static -fno-stack-protector \
          -fno-tree-loop-distribute-patterns -fwhole-program -fno-strict-aliasing \
          -fno-asynchronous-unwind-tables -fno-ident \
          -Wl,-T,"$DIR/mereo.lds" -s -o "$DIR/.x25519" "$DIR/.x25519.c" 2>/dev/null; then
    got=$("$DIR/.x25519" | od -An -tx1 | tr -d ' \n')
    [ "$got" = "$X25519_RFC7748" ] \
        && echo "  x25519 against RFC 7748 s5.2: ok" \
        || { echo "  x25519 against RFC 7748 s5.2 FAIL"; echo "    got  $got";
             echo "    want $X25519_RFC7748"; rc=1; }
else
    echo "  x25519 build FAIL"; rc=1
fi
rm -f "$DIR/.x25519" "$DIR/.x25519.c"
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
