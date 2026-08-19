#!/usr/bin/env bash
# Suite 4 -- mereo namespaces against C++ namespaces.
#
# The claim is that mereo's namespace IS a namespace in the sense C++ means, not
# a mandatory prefix. The way to check a claim like that is to write the same
# program twice and compare what it prints, so `cases.mereo` and `cases.cpp` are
# the same nine questions asked of each language:
#
#   1  a top-level name, reachable even though a namespace declares that name too
#   2  a namespace member of the same name -- a DIFFERENT type
#   3  a nested namespace, the name a third time
#   4  a sibling namespace, a fourth
#   5  outward lookup: an inner namespace calling the outer one's member, bare
#   6  shadowing: the inner declaration wins over a top-level one
#   7  reopening a namespace and adding to it
#   8  qualified access from outside, at every depth
#   9  unqualified access from inside
#
# Each answer is chosen so a WRONG resolution gives a different number: the four
# `rec`s differ in width and byte order, and the templates add 1, 100 and 1000.
# Agreement by luck is not available.
#
# What is NOT compared, because mereo does not have it and says so: `using`,
# namespace aliases, anonymous namespaces (one flat program, no linkage to
# hide), and argument-dependent lookup (no overloading to resolve).
#
#   ./tests/namespaces/run.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
HERE="$DIR/tests/namespaces"
OUT=${OUT:-/tmp/mbuild/ns}; mkdir -p "$OUT"

CFLAGS="-O2 -nostdlib -static -fno-stack-protector -fwhole-program"
CFLAGS="$CFLAGS -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident"
CFLAGS="$CFLAGS -Wl,-T,$DIR/mereo.lds -Wl,-z,noseparate-code -Wl,--build-id=none -s"

fail=0
if ! python3 "$DIR/mereoc.py" "$HERE/cases.mereo" > "$OUT/cases.c" 2>"$OUT/err"; then
    echo "  namespaces  MEREO FAILED  $(tail -1 "$OUT/err")"; exit 1
fi
gcc $CFLAGS -o "$OUT/m" "$OUT/cases.c" 2>"$OUT/gcc" || {
    echo "  namespaces  GCC FAILED  $(tail -1 "$OUT/gcc")"; exit 1; }
g++ -O2 -o "$OUT/cpp" "$HERE/cases.cpp" 2>"$OUT/g++" || {
    echo "  namespaces  G++ FAILED  $(tail -1 "$OUT/g++")"; exit 1; }

m=$("$OUT/m"); c=$("$OUT/cpp")
if [ "$m" = "$c" ]; then
    echo "  namespaces vs C++: agree  ($m)"
else
    echo "  namespaces vs C++: DIFFER"
    echo "      mereo: $m"
    echo "      c++  : $c"
    fail=1
fi
exit $fail
