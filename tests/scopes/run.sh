#!/usr/bin/env bash
# RAII scope-parity runner. For each scenario NN_name there is a .mereo and a
# .cpp expressing the SAME resource/scope structure; each resource closes a
# sentinel fd (101=a,102=b,...) on release. We strace the close() calls of both
# binaries and assert mereo's release order equals C++'s. That makes "mereo's
# scope RAII matches C++" a checked, byte-for-byte invariant.
#
#   ./run.sh            run every scenario
#   ./run.sh 01 03      run just these
set -u
DIR=$(dirname "$(readlink -f "$0")")
B=${OUT:-/tmp/mbuild/scopes}; mkdir -p "$B"
MFLAGS="-O2 -fwrapv -nostdlib -static -fno-stack-protector -fno-tree-loop-distribute-patterns -fwhole-program -fno-strict-aliasing"
XFLAGS="-O2 -fwrapv -nostdlib -ffreestanding -fno-exceptions -fno-rtti -static -fno-stack-protector"

closes () { strace -e trace=close "$1" 2>&1 | grep -oE 'close\(10[0-9]\)' | tr '\n' ' '; }

scenarios=()
if [ $# -gt 0 ]; then
    for n in "$@"; do scenarios+=("$(ls "$DIR/${n}_"*.mereo 2>/dev/null | head -1)"); done
else
    for f in "$DIR"/[0-9][0-9]_*.mereo; do scenarios+=("$f"); done
fi

pass=0 fail=0 pend=0
for m in "${scenarios[@]}"; do
    [ -f "$m" ] || continue
    base=$(basename "$m" .mereo); cpp="$DIR/$base.cpp"
    # mereo side
    if ! python3 "$DIR/../../mereoc.py" "$m" > "$B/$base.c" 2>"$B/$base.mereo.err"; then
        printf '  %-26s PENDING (mereo rejects: %s)\n' "$base" "$(tail -1 "$B/$base.mereo.err" | sed "s/^mereoc: error: //")"
        pend=$((pend+1)); continue
    fi
    gcc $MFLAGS -o "$B/$base.m" "$B/$base.c" 2>/dev/null || { printf '  %-26s FAIL (mereo C did not build)\n' "$base"; fail=$((fail+1)); continue; }
    # c++ side
    g++ $XFLAGS -o "$B/$base.x" "$cpp" 2>/dev/null || { printf '  %-26s FAIL (c++ did not build)\n' "$base"; fail=$((fail+1)); continue; }
    mo=$(closes "$B/$base.m"); xo=$(closes "$B/$base.x")
    if [ "$mo" = "$xo" ]; then printf '  %-26s ok   [%s]\n' "$base" "${mo% }"; pass=$((pass+1))
    else printf '  %-26s MISMATCH\n     mereo: [%s]\n     c++:   [%s]\n' "$base" "${mo% }" "${xo% }"; fail=$((fail+1)); fi
done
echo "---"
echo "parity: $pass ok, $fail mismatch, $pend pending"
exit $((fail > 0))
