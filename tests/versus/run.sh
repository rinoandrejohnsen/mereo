#!/usr/bin/env bash
# Suite 3 -- mereo VERSUS C, on the generated machine code.
#
# The project's claim is that what you write is what the machine does: no
# runtime, no hidden control flow, and abstractions -- the release tower,
# `ensure`, scopes, views, spans -- that cost nothing a careful C programmer
# would not also pay. This suite makes that claim falsifiable.
#
# Each case is a PAIR: `cases/NAME.mereo` and `cases/NAME.c`. Both are built
# freestanding with the shipped flags and the shipped linker script, then
# compared on what a cost actually is: HOW MANY of each instruction, and how
# many bytes of `.text`.
#
# WHY THE HISTOGRAM AND NOT THE BYTES. Byte-identity was the first criterion and
# the first case disproved it: two twins doing identical work landed on
# different bytes because GCC picked %r9 where it had picked %r8 and put a
# temporary at a different stack offset. Neither is a cost. The instruction
# SEQUENCE was the second try, and `loop_sum` disproved that too -- same
# instructions, same count, same size, two of them scheduled in the other order.
# What is left is the multiset, which is exactly what cost means: an extra check
# is a `cmp` and a `jump`, a spill is a `mov`, a missed strength reduction is an
# `imul` where a `shl` belonged. Register allocation and scheduling are not.
# Byte-identity is still reported when it happens, as the stronger result it is.
#
# THE BASELINE IS CORRECT C, NOT MERELY EQUIVALENT C. The claim being tested is
# that mereo is as fast as a hand-written C program that is RIGHT as a Linux
# program: what it opens it closes, on every path out including every failure;
# a call that can fail is checked; a failure is reported rather than swallowed.
# C that leaks a descriptor on an error path is cheaper than mereo and is not a
# comparison worth making, because mereo cannot write that program -- its
# cleanup is derived, so the leak is not available to it even as a mistake.
#
# THREE RULES ENFORCE THAT, all mechanical:
#
#   1. Both binaries must be LINUX-CORRECT, audited by `mereoraii` -- the same
#      tool that audits mereo binaries, working on the syscall stream and so
#      indifferent to which language produced it. It runs each once for leaks
#      and double-closes, then injects a failure at each fallible call in turn
#      and requires the cleanup to close what was open and report it. A twin
#      that skips a close on one error path is rejected before its code is ever
#      looked at.
#
#   2. Both must BEHAVE the same -- same bytes on stdout and stderr, same exit
#      status, on the same input. Note the limit: nothing here sends a SIGNAL,
#      so this rule alone would not catch a missing interrupt stub. It did not:
#      the `open_close` twin was 20 instructions ahead until the disassembly
#      showed it had no stub to install one.
#
#   3. The twin must do the same WORK, which is the part no tool can check. It
#      is written out by hand and kept readable, so a reader can judge whether
#      it is the C they would have written.
#
# AND ONE RULE THAT CANNOT BE ENFORCED, only kept: each twin is written from the
# PROBLEM -- the syscalls to make, the checks to run, the records to print --
# and never by transcribing mereoc's output. Copying the generated C would make
# every case pass and prove nothing. Knowing the specification mereo implements
# (the record format, the stage numbering, which errno values end a program
# cleanly) is not the same as copying its instruction selection.
#
# THE BASELINE. `baseline.txt` records where each case stands today. The suite
# fails on DRIFT, in either direction, because a case getting better is as much
# a thing to look at as a case getting worse. `--bless` rewrites it, and the
# diff it produces is the thing to read in review.
#
#   ./tests/versus/run.sh              every case
#   ./tests/versus/run.sh open_close   just these
#   ./tests/versus/run.sh --keep       leave artifacts in $OUT for reading
#   ./tests/versus/run.sh --bless      re-record baseline.txt
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
HERE="$DIR/tests/versus"
OUT=${OUT:-/tmp/mbuild/versus}; mkdir -p "$OUT"
BASE="$HERE/baseline.txt"

# the shipped build, flag for flag -- the same list build.sh uses, because a
# comparison under different flags is a comparison of the flags
CFLAGS="-O2 -nostdlib -static -fno-stack-protector -fno-tree-loop-distribute-patterns"
CFLAGS="$CFLAGS -fwhole-program -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident"
CFLAGS="$CFLAGS -Wl,-T,$DIR/mereo.lds -Wl,-z,noseparate-code -Wl,--build-id=none -s"

# How each case is RUN, so behaviour can be compared as well as code:
# "case|stdin|args". A case with no entry runs with no input and no arguments.
RUNS=(
  "read_write|lorem ipsum|"
  "span_scan|alpha:beta:gamma|"
  "index_fast|the quick brown fox jumps over the lazy dog|"
  "index_safe|the quick brown fox jumps over the lazy dog|"
)

# The recorded numbers are a property of THIS COMPILER as much as of mereo:
# instruction counts move with GCC's register allocator and inliner. A baseline
# taken elsewhere is not a regression, so it is not reported as one -- the
# toolchain is recorded beside the numbers and compared.
TOOLCHAIN=$(gcc --version | head -1)
BASE_TOOLCHAIN=$(sed -n 's/^# toolchain: //p' "$BASE" 2>/dev/null)
SAME_TOOLCHAIN=1
[ -n "$BASE_TOOLCHAIN" ] && [ "$BASE_TOOLCHAIN" != "$TOOLCHAIN" ] && SAME_TOOLCHAIN=0

KEEP=0 BLESS=0; ARGS=()
for a in "$@"; do
    case "$a" in
        --keep)  KEEP=1 ;;
        --bless) BLESS=1 ;;
        *) ARGS+=("$a") ;;
    esac
done

runspec() {  # runspec CASE -> "stdin<TAB>args"
    local c=$1 e rest
    for e in "${RUNS[@]}"; do
        [ "${e%%|*}" = "$c" ] || continue
        rest=${e#*|}; printf '%s\t%s' "${rest%%|*}" "${rest#*|}"; return
    done
    printf '\t'
}

# Cases where mereo legitimately makes more syscalls than its twin, and what the
# extra work buys. Measured, each of them -- the number in the reason is what
# removing the cause actually produced, not an estimate.
waiver() {
    case "$1" in
    layout_view)
        echo "the per-stage \`# stage N\` markers are distinct, so GCC cannot"\
             "tail-merge two otherwise identical error blocks; stripping them"\
             "drops mereo to the twin's count exactly. They are what lets"\
             "mereocheck verify hot/cold layout on the shipped assembly." ;;
    *) echo "" ;;
    esac
}

# the instruction multiset: mnemonic and how many, sorted. Not the sequence.
histogram() { objdump -d --no-show-raw-insn "$1" \
              | sed -n 's/^ *[0-9a-f]*:\t\([a-z0-9.]*\).*/\1/p' \
              | sort | uniq -c | awk '{print $2, $1}'; }

pass=0 fail=0
declare -A NEW=()
cases=()
if [ ${#ARGS[@]} -gt 0 ]; then
    for a in "${ARGS[@]}"; do cases+=("$HERE/cases/$a.mereo"); done
else
    for f in "$HERE"/cases/*.mereo; do cases+=("$f"); done
fi

for src in "${cases[@]}"; do
    name=$(basename "$src" .mereo)
    twin="$HERE/cases/$name.c"
    if [ ! -f "$src" ] || [ ! -f "$twin" ]; then
        printf '  %-18s NO PAIR (need cases/%s.mereo and cases/%s.c)\n' \
               "$name" "$name" "$name"; fail=$((fail+1)); continue
    fi

    # ---- build both, from the same flags
    if ! python3 "$DIR/mereoc.py" "$src" > "$OUT/$name.mereo.c" 2>"$OUT/$name.err"; then
        printf '  %-18s MEREO FAILED  %s\n' "$name" \
               "$(tail -1 "$OUT/$name.err")"; fail=$((fail+1)); continue
    fi
    if ! gcc $CFLAGS -o "$OUT/$name.m" "$OUT/$name.mereo.c" 2>"$OUT/$name.gcc"; then
        printf '  %-18s MEREO C DID NOT COMPILE\n' "$name"; fail=$((fail+1)); continue
    fi
    if ! gcc $CFLAGS -o "$OUT/$name.c.bin" "$twin" 2>"$OUT/$name.twin.gcc"; then
        printf '  %-18s TWIN DID NOT COMPILE  %s\n' "$name" \
               "$(head -1 "$OUT/$name.twin.gcc")"; fail=$((fail+1)); continue
    fi

    # ---- BEHAVIOUR first: a twin that does less has no business being compared.
    #      Through files, not command substitution: several cases write raw
    #      bytes, and $( ) eats NULs and trailing newlines.
    IFS=$'\t' read -r stdin args <<<"$(runspec "$name")"
    # shellcheck disable=SC2086
    (cd "$DIR" && printf '%s' "$stdin" | timeout 10 "$OUT/$name.m" $args) \
        >"$OUT/$name.m.out" 2>"$OUT/$name.m.err"; mrc=$?
    # shellcheck disable=SC2086
    (cd "$DIR" && printf '%s' "$stdin" | timeout 10 "$OUT/$name.c.bin" $args) \
        >"$OUT/$name.c.out" 2>"$OUT/$name.c.err"; crc=$?
    if [ "$mrc" != "$crc" ] || ! cmp -s "$OUT/$name.m.out" "$OUT/$name.c.out" \
       || ! cmp -s "$OUT/$name.m.err" "$OUT/$name.c.err"; then
        printf '  %-18s BEHAVIOUR DIFFERS  exit mereo=%s c=%s%s%s\n' "$name" \
            "$mrc" "$crc" \
            "$(cmp -s "$OUT/$name.m.out" "$OUT/$name.c.out" || echo ', stdout')" \
            "$(cmp -s "$OUT/$name.m.err" "$OUT/$name.c.err" || echo ', stderr')"
        fail=$((fail+1)); continue
    fi

    # ---- LINUX-CORRECTNESS, on both sides, before the code is compared.
    #
    #      The baseline is not "some C that produces the same output" -- it is C
    #      that is CORRECT as a Linux program: what it opens it closes, on every
    #      path including every failure, and a failure is reported rather than
    #      swallowed. C that leaks a descriptor on an error path would be
    #      cheaper than mereo and would not be a comparison worth making, since
    #      mereo cannot write that program.
    #
    #      `mereoraii` is the same tool that audits mereo binaries, and it works
    #      on the syscall stream rather than on anything mereo-specific, so it
    #      audits the twin equally: run once for leaks, then inject a failure at
    #      each fallible call in turn and require the cleanup to close what was
    #      open. Both binaries must pass. Cases that open nothing have nothing
    #      for it to check and are skipped by the tool itself.
    for side in m c.bin; do
        if ! python3 "$DIR/mereoraii.py" -- "$OUT/$name.$side" >/dev/null 2>&1; then
            printf '  %-18s NOT LINUX-CORRECT (%s): leaks a descriptor or\n' \
                   "$name" "$([ "$side" = m ] && echo mereo || echo 'C twin')"
            printf '  %-18s   fails to report on some fault path\n' ""
            fail=$((fail+1)); continue 2
        fi
    done

    # ---- ...and only then, the code
    histogram "$OUT/$name.m"     > "$OUT/$name.m.hist"
    histogram "$OUT/$name.c.bin" > "$OUT/$name.c.hist"
    objcopy -O binary --only-section=.text "$OUT/$name.m"     "$OUT/$name.m.text"
    objcopy -O binary --only-section=.text "$OUT/$name.c.bin" "$OUT/$name.c.text"
    msz=$(stat -c%s "$OUT/$name.m.text"); csz=$(stat -c%s "$OUT/$name.c.text")
    mn=$(awk '{s+=$2} END{print s+0}' "$OUT/$name.m.hist")
    cn=$(awk '{s+=$2} END{print s+0}' "$OUT/$name.c.hist")
    msys=$(awk '$1=="syscall"{print $2}' "$OUT/$name.m.hist"); msys=${msys:-0}
    csys=$(awk '$1=="syscall"{print $2}' "$OUT/$name.c.hist"); csys=${csys:-0}

    NEW[$name]="$mn $msz $cn $csz"
    want=$(awk -v n="$name" '$1==n {print $2, $3, $4, $5}' "$BASE" 2>/dev/null)
    got="$mn $msz $cn $csz"

    # A hard rule: mereo must never make MORE system calls than the C doing the
    # same job. That is not allocation noise, it is extra work.
    #
    # A case may be WAIVED, but only with a reason saying what the extra work
    # buys -- a waiver is a claim, not a way to make a number go away, and it is
    # printed on every run so it stays argued rather than forgotten.
    if [ "$msys" -gt "$csys" ]; then
        why=$(waiver "$name")
        if [ -z "$why" ]; then
            printf '  %-18s EXTRA SYSCALLS  mereo %s, C %s\n' "$name" "$msys" "$csys"
            fail=$((fail+1)); continue
        fi
        printf '  %-18s waived +%s syscall(s): %s\n' "$name" "$((msys - csys))" "$why"
    fi

    if [ "$BLESS" = 1 ]; then
        printf '  %-18s recorded     mereo %s insns/%s B, C %s insns/%s B\n' \
               "$name" "$mn" "$msz" "$cn" "$csz"; pass=$((pass+1)); continue
    fi
    if [ -n "$want" ] && [ "$want" != "$got" ]; then
        if [ "$SAME_TOOLCHAIN" = 0 ]; then
            printf '  %-18s mereo %+d insns, %+d B   (baseline is another compiler)\n' \
                   "$name" "$((mn - cn))" "$((msz - csz))"; pass=$((pass+1)); continue
        fi
        printf '  %-18s DRIFTED      was [%s], now [%s]  (--bless to accept)\n' \
               "$name" "$want" "$got"; fail=$((fail+1)); continue
    fi
    if [ -z "$want" ]; then
        printf '  %-18s NO BASELINE  %s insns/%s B vs %s insns/%s B (--bless)\n' \
               "$name" "$mn" "$msz" "$cn" "$csz"; fail=$((fail+1)); continue
    fi

    if cmp -s "$OUT/$name.m.hist" "$OUT/$name.c.hist"; then
        if cmp -s "$OUT/$name.m.text" "$OUT/$name.c.text"; then
            printf '  %-18s identical    %s insns, %s B (bytes too)\n' "$name" "$mn" "$msz"
        else
            printf '  %-18s same work    %s insns, %s B\n' "$name" "$mn" "$msz"
        fi
    else
        printf '  %-18s mereo %+d insns, %+d B   %s\n' "$name" \
               "$((mn - cn))" "$((msz - csz))" \
               "$(join -a1 -a2 -e0 -o 0,1.2,2.2 "$OUT/$name.c.hist" "$OUT/$name.m.hist" \
                  | awk '$2!=$3 {printf "%s%+d ", $1, $3-$2}')"
    fi
    pass=$((pass+1))
done

if [ "$BLESS" = 1 ]; then
    { echo "# mereo vs C -- where each case stands. Regenerate with --bless."
      echo "# toolchain: $TOOLCHAIN"
      echo "# name  mereo_insns  mereo_bytes  c_insns  c_bytes"
      for k in $(printf '%s\n' "${!NEW[@]}" | sort); do
          printf '%-18s %s\n' "$k" "${NEW[$k]}"; done
    } > "$BASE"
    echo "  (baseline.txt rewritten)"
fi
[ "$KEEP" = 1 ] && echo "  (artifacts in $OUT)"
echo "---"
echo "versus: $pass ok, $fail differing"
[ "$fail" = 0 ]
