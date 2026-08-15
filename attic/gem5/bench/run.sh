#!/usr/bin/env bash
# run.sh -- build the packed-vs-normal benchmarks and measure them, on the real
# CPU and (optionally) on the simulated Raptor Cove P-core.
#
#   ./run.sh            build + measure on hardware (perf, pinned to core 0)
#   ./run.sh --gem5     ... and also under gem5/raptorcove.py
#
# Every pair below is ONE source compiled twice, differing only in -DPACKED.
# That is the whole point: any difference in the numbers comes from the layout,
# not from the code.
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
CF="-std=c++20 -O2 -nostdlib -static -fno-exceptions -fno-rtti -fno-stack-protector
    -fwhole-program -fno-tree-loop-distribute-patterns -fno-strict-aliasing"
B=${OUT:-/tmp/pkbench}; mkdir -p "$B"

# name         source   N        passes   what it isolates
CASES="
tiny   pk.cpp   512    64   both layouts fit L1d -- footprint cannot help
small  pk.cpp   4096    8   packed fits L1d (45K), normal does not (98K)
large  pk.cpp   200000  3   packed nearly fits L2 (2.2M), normal does not (4.8M)
asmall al.cpp   4096    8   fields already align -- packed changes nothing
alarge al.cpp   200000  3   same, at L2 scale
vec    vec.cpp  0       0   a loop GCC vectorises
one    one.cpp  0       0   ONE hot struct: pure misalignment, no footprint change
"

echo "== building =="
printf '%s\n' "$CASES" | while read -r name src n passes _rest; do
    [ -z "${name:-}" ] && continue
    for v in normal packed; do
        d=""; [ "$v" = packed ] && d="-DPACKED"
        extra=""; [ "$n" != 0 ] && extra="-DN=$n -DPASSES=$passes"
        g++ $CF $extra $d -o "$B/${name}_$v" "$DIR/$src" || echo "  FAILED $name/$v"
    done
    printf '  %-7s %s\n' "$name" "$_rest"
done
g++ $CF -o "$B/nul" "$DIR/nul.cpp"      # empty program: process-startup cost

cycles () {  # cycles:u for one binary, pinned, best of 7
    taskset -c 0 perf stat -e cycles:u -r 7 "$1" 2>&1 >/dev/null \
        | grep -oE '^\s+[0-9,]+\s+cpu_core/cycles' | tr -d ' ,' | grep -oE '^[0-9]+'
}

echo
echo "== real hardware (perf, pinned to core 0, best of 7) =="
printf '  startup baseline (empty program): %s cycles\n\n' "$(cycles "$B/nul")"
printf '  %-8s %13s %13s %9s\n' case normal packed delta
printf '%s\n' "$CASES" | while read -r name _src _n _p _rest; do
    [ -z "${name:-}" ] && continue
    n=$(cycles "$B/${name}_normal"); p=$(cycles "$B/${name}_packed")
    [ -n "$n" ] && [ -n "$p" ] && printf '  %-8s %13s %13s %8s%%\n' "$name" "$n" "$p" \
        "$(awk -v a="$n" -v b="$p" 'BEGIN{printf "%+.1f",(b-a)/a*100}')"
done

[ "${1:-}" = "--gem5" ] || exit 0
G=/home/rino/gem5/build/X86/gem5.opt
[ -x "$G" ] || { echo; echo "gem5 not built at $G"; exit 1; }
export LD_LIBRARY_PATH=/tmp/py311/usr/lib PYTHONHOME=/tmp/py311/usr

echo
echo "== simulated Raptor Cove P-core =="
echo "   NOTE: gem5 runs 2.3x-12.4x slower than this silicon and the error is NOT"
echo "   uniform -- it correlates with split accesses, i.e. with the very thing"
echo "   these benchmarks test. Trust the hardware column for alignment questions."
printf '  %-8s %13s %13s %9s\n' case normal packed delta
printf '%s\n' "$CASES" | while read -r name _src _n _p _rest; do
    [ -z "${name:-}" ] && continue
    for v in normal packed; do
        "$G" --outdir="$B/m5_${name}_$v" "$DIR/../raptorcove.py" \
             --cmd="$B/${name}_$v" >/dev/null 2>&1
    done
    n=$(awk '/^system.cpu.numCycles/{print $2; exit}' "$B/m5_${name}_normal/stats.txt" 2>/dev/null)
    p=$(awk '/^system.cpu.numCycles/{print $2; exit}' "$B/m5_${name}_packed/stats.txt" 2>/dev/null)
    [ -n "${n:-}" ] && [ -n "${p:-}" ] && printf '  %-8s %13s %13s %8s%%\n' "$name" "$n" "$p" \
        "$(awk -v a="$n" -v b="$p" 'BEGIN{printf "%+.1f",(b-a)/a*100}')"
done
