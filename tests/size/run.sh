#!/usr/bin/env bash
# Where mereo's extra bytes actually are.
#
# `docs/exam.md` said for months that mereo is bigger than its hand-written C
# twin "because the extra sits in cold paths -- the report, the error blocks,
# the release tower -- and never runs". Nothing measured that, and by the time
# it was measured the figures in the doc had drifted by 150 instructions without
# anyone noticing, which is what an unchecked claim does.
#
# This attributes EVERY byte. `tools/coldsplit.py` builds with `-g`, walks the
# disassembly with `objdump -dl` so each instruction carries the generated-C
# line it came from, and splits at the first `error_*:` label -- mereoc emits
# the whole tower after the spine in one run, so that line is an exact boundary
# and not a guess. Unattributed bytes must be zero: if `objdump` cannot place an
# instruction, the split is not trustworthy and this fails rather than rounding.
#
# The bands below are deliberately wide. They exist to catch a DRIFT -- the
# cold tower quietly growing into the hot path, or the spine doubling -- not to
# pin a number that legitimate work will move.
#
#   ./tests/size/run.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
OUT=${OUT:-/tmp/mereo_size}; mkdir -p "$OUT"
CF="-fwrapv -nostdlib -static -fno-stack-protector -fno-tree-loop-distribute-patterns"
CF="$CF -fwhole-program -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident"
LD="-Wl,-T,$DIR/mereo.lds"
fail=0

python3 "$DIR/mereoc.py" "$DIR/exam/mereo/loglyze.mereo" > "$OUT/m.c" 2>/dev/null \
  || { echo "size: the exam does not transpile"; exit 1; }
gcc -O2 -g $CF $LD -o "$OUT/m.dbg" "$OUT/m.c"            2>/dev/null
gcc -O2 -g $CF $LD -o "$OUT/c.dbg" "$DIR/exam/c/loglyze.c" 2>/dev/null
[ -x "$OUT/m.dbg" ] && [ -x "$OUT/c.dbg" ] || { echo "size: build failed"; exit 1; }

read -r _ SPINE _ < <(python3 "$DIR/tools/coldsplit.py" --tsv "$OUT/m.c" "$OUT/m.dbg" | sed -n 1p)
read -r _ COLD  _ < <(python3 "$DIR/tools/coldsplit.py" --tsv "$OUT/m.c" "$OUT/m.dbg" | sed -n 2p)
read -r _ LOST  _ < <(python3 "$DIR/tools/coldsplit.py" --tsv "$OUT/m.c" "$OUT/m.dbg" | sed -n 3p)
CTEXT=$(size -A "$OUT/c.dbg" | awk '/^\.text/{print $2}')
MTEXT=$((SPINE + COLD))

printf '  %-34s %s\n' "mereo .text"          "$MTEXT bytes"
printf '  %-34s %s\n' "  ...spine, which runs"  "$SPINE bytes"
printf '  %-34s %s\n' "  ...cold tower"         "$COLD bytes"
printf '  %-34s %s\n' "  ...unattributed"       "$LOST bytes"
printf '  %-34s %s\n' "C twin .text"            "$CTEXT bytes"
printf '  %-34s %s%%\n' "spine over the C twin" "$(( (SPINE - CTEXT) * 100 / CTEXT ))"

# 1. every byte placed, or the split means nothing
[ "$LOST" = 0 ] || { echo "  FAIL  $LOST bytes could not be attributed"; fail=1; }
# 2. the cold tower is a small part of the binary -- if this grows, the claim
#    that mereo's size is cold has quietly become true in the wrong direction
[ "$COLD" -lt $((MTEXT / 4)) ] || { echo "  FAIL  cold tower is over a quarter of .text"; fail=1; }
# 3. ...and the SPINE is what the difference against C actually is. This is the
#    number docs/exam.md must quote, and the band catches it doubling.
[ "$SPINE" -lt $((CTEXT * 2)) ] || { echo "  FAIL  spine is more than twice the C twin"; fail=1; }
[ "$SPINE" -gt "$CTEXT" ] || printf '  note: the spine is no larger than the C twin -- docs/exam.md should say so\n'

echo "---"
[ "$fail" = 0 ] && echo "size: every byte attributed; the difference is in the spine, not the tower" \
                || echo "size: FAILED"
exit "$fail"
