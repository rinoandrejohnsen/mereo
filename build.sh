#!/usr/bin/env bash
# build.sh -- transpile and compile the mereo programs, and for every crossroad
# program (one with `LABEL likely goes` roads) VERIFY the hot/cold layout on the
# actual assembly with mereocheck. A layout violation fails the build.
#
#   ./build.sh                       build every program in the project
#   ./build.sh examples/branch.mereo  build just these
#   OUT=/tmp/mb ./build.sh     put artifacts elsewhere (default: ./build)
#
# A program is a .mereo whose top form is `program ...`; the rest (linux.mereo,
# core.mereo) are the two LIBRARIES, which live at the root and are pulled in with
# `use`. Programs live in the directories below -- none at the root.

set -u
DIR=$(dirname "$(readlink -f "$0")")
OUT=${OUT:-$DIR/build}
# -fno-tree-loop-distribute-patterns: a mereo program is freestanding AND
# function-free -- there is no C library to call. Given honest pointer
# arithmetic (see deref_addr), GCC recognizes a byte-copy loop and rewrites it
# into a `memcpy` CALL, which then fails to link. Same reason the kernel builds
# with it. It changes nothing else: with it added, every binary in the corpus
# was byte-identical.
#
# -fwhole-program: this IS the whole program -- one translation unit, no library
# behind it. It needs `externally_visible` on _start/_run (mereoc emits it), or
# the entry symbol is internalized and deleted. Measured: all 60 binaries came
# out byte-identical, because every helper is already `static inline
# always_inline` -- there is no external linkage left for it to exploit. Kept as
# a true statement of the build, not for a win it cannot deliver.
#
# -fno-strict-aliasing: a byte-grain field access lowers to C's punning idiom --
# `*(unsigned short *)(buf + 1)` over a `char[8]` -- which is formally UB under
# the strict-aliasing rule mereo's memory model ignores by design (bits are bits;
# the VIEW says how to read them). GCC handles char-array punning in practice,
# but the guarantee is free: with the flag added every binary in the corpus was
# byte-identical, so this buys correctness-by-the-standard at zero cost.
#
# -fwrapv: a mereo scalar is a C `long`, so `n is n + 1` at LONG_MAX is signed
# overflow -- undefined, and an optimiser is entitled to assume it cannot happen.
# This makes it defined two's-complement wrapping instead. It DETECTS nothing;
# what it buys is that the program still means something at the edge, and the
# access analysis can reason about an index that wraps rather than having to
# treat the whole expression as unreachable. The expectation was that it would
# cost, since assuming an induction variable never wraps is exactly what a loop
# optimiser wants. Measured the other way: 377248 bytes against 379168 across 89
# binaries, 75.4 ms against 77.4 ms over 800M byte-loads, and 42 vector
# instructions either way. Smaller, no slower, identically vectorised.
#
# The last two say what a freestanding program does NOT have: no unwind tables
# (mereo's cleanup is the release tower, which is ordinary jumps -- nothing ever
# reads a CFI record) and no compiler version string. Measured: -fno-ident
# leaves .text byte-identical everywhere. -fno-asynchronous-unwind-tables leaves
# the INSTRUCTIONS identical everywhere -- in the four TLS binaries 14 bytes
# move, all of them the displacement field of a rip-relative reference to a
# static-storage symbol, because dropping .eh_frame shifted .bss. Normalise the
# displacements and the two disassemblies are the same file.
CFLAGS="-fwrapv -nostdlib -static -fno-stack-protector -fno-tree-loop-distribute-patterns -fwhole-program -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident"

# ...and mereo.lds says what it DOES have, which is where the file size goes:
# the stock script lays out a C program with a loader and pays for it in
# page-aligned segments a mereo binary never fills. See the comment in the
# script. `-s` is for the shipped binary only -- the .dbg build below drops it
# and keeps its DWARF, so mereocheck verifies the layout that actually ships.
LDFLAGS="-Wl,-T,$DIR/mereo.lds -Wl,-z,noseparate-code -Wl,--build-id=none"
mkdir -p "$OUT"

# Nothing is skipped any more. `examples/showcase.mereo` exists for the
# highlighter, but it is a REAL program -- it builds and runs like the rest,
# which the two files it replaced (`ex`, `example_syntax`) never did.
SHOWCASES=" "

# Every program directory. Everything here is gated the same way -- transpile, compile, and for a crossroad program verify
# the hot/cold layout on the real assembly. The scope scenarios and tls/ went
# ungated for a while, which is exactly how scopes/14 kept a `when` road whose guard was a
# compile-time constant: the branch folded away, so the scenario had not been
# testing a branch at all. A gate that skips a directory does not protect it.
SUBDIRS="examples tests/scopes programs/tls"

# argument list -> the programs to build; default is every `program` .mereo
if [ $# -gt 0 ]; then
    progs=("$@")
else
    progs=()
    for d in $SUBDIRS; do
        for f in "$DIR${d:+/$d}"/*.mereo; do
            [ -f "$f" ] || continue
            name=$(basename "$f" .mereo)
            case "$SHOWCASES" in *" $name "*) continue ;; esac
            grep -q '^program\( \|$\)' "$f" && progs+=("${d:+$d/}$(basename "$f")")
        done
    done
fi

fails=0
checked=0
for src in "${progs[@]}"; do
    name=$(basename "$src" .mereo)
    # `src` carries its directory, so a subdirectory program can also be named
    # on the command line -- rebuilding the path from the basename could only
    # ever find the repo root, which is half of why those directories went
    # unbuilt. Basenames are unique across them, so artifacts stay flat.
    label=${src%.mereo}
    c="$OUT/$name.c"

    if ! python3 "$DIR/mereoc.py" "$DIR/$src" > "$c" 2>"$OUT/$name.err"; then
        printf '  %-26s TRANSPILE FAIL\n' "$label"; sed 's/^/    /' "$OUT/$name.err"
        fails=$((fails + 1)); continue
    fi
    if ! gcc -O2 $CFLAGS $LDFLAGS -s -o "$OUT/$name" "$c" 2>"$OUT/$name.err"; then
        printf '  %-26s COMPILE FAIL\n' "$label"; sed 's/^/    /' "$OUT/$name.err"
        fails=$((fails + 1)); continue
    fi

    # crossroad program? the generated C carries `LABEL_road_k` labels. Verify
    # the layout on a -g build at the SAME optimization the binary ships at.
    if grep -q '_road_' "$c"; then
        checked=$((checked + 1))
        gcc -O2 -g $CFLAGS $LDFLAGS -o "$OUT/$name.dbg" "$c" 2>/dev/null
        if python3 "$DIR/mereocheck.py" "$OUT/$name.dbg" "$c" > "$OUT/$name.chk" 2>&1; then
            printf '  %-26s ok  (layout verified)\n' "$label"
        else
            printf '  %-26s LAYOUT VIOLATION\n' "$label"
            grep -E 'FAIL|VIOLATION' "$OUT/$name.chk" | sed 's/^ */    /'
            fails=$((fails + 1))
        fi
    else
        printf '  %-26s ok\n' "$label"
    fi
done

# tidy transient logs -- artifacts kept are .c, the binary, and .dbg (the -g
# build mereocheck/mereodis read) for crossroad programs
find "$OUT" -name '*.err' -empty -delete 2>/dev/null
find "$OUT" -name '*.chk' -delete 2>/dev/null

echo "---"
echo "built ${#progs[@]} program(s), $checked crossroad-verified, $fails failure(s)"
exit $((fails > 0))
