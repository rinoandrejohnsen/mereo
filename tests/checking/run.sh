#!/usr/bin/env bash
# Suite 5 -- what each language DECIDES, against C++ with concepts and Zig.
#
# The other suites ask whether mereo is correct or what it costs. This one asks
# what its compiler catches, and it needs a different oracle: a mistake written
# three times, once per language, and compiled by each.
#
# Two things are recorded, because "refused" alone is not the interesting part:
#
#   OUTCOME   refused, warned (it still compiles), or accepted silently
#   AT SITE   does the first diagnostic point at the line the mistake is ON?
#
# The second is the whole argument about `concept` and about deriving a port's
# requirement. A diagnostic that names a template's own line, two levels from
# the call, is a worse answer to the same question -- and it is what Zig gives
# for `anytype`, and what C++ gave before concepts.
#
# Every case file carries the marker `MISTAKE` on exactly the offending line, so
# the expected line number is read from the source rather than written down
# twice.
#
#   ./tests/checking/run.sh            every case
#   ./tests/checking/run.sh port_receiver
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
HERE="$DIR/tests/checking"
OUT=${OUT:-/tmp/mbuild/checking}; mkdir -p "$OUT"

have_zig=1; command -v zig >/dev/null || have_zig=0

# the line the marker sits on
mistake_line () { grep -n 'MISTAKE' "$1" | head -1 | cut -d: -f1; }

# -> "refused <line>" | "accepted"
run_mereo () {
    if python3 "$DIR/mereoc.py" "$1" >/dev/null 2>"$OUT/e"; then echo "accepted"; return; fi
    echo "refused $(sed -n 's/.*[Ll]ine \([0-9]\+\):.*/\1/p' "$OUT/e" | head -1)"
}
run_cpp () {
    # three outcomes, not two: a WARNING still compiles, and treating it as a
    # refusal would flatter every language that only warns
    if g++ -std=c++20 -O2 -Wall -Wextra -fsyntax-only "$1" >/dev/null 2>"$OUT/e"; then
        local w; w=$(grep -oE ':[0-9]+:[0-9]+: warning' "$OUT/e" | head -1 | cut -d: -f2)
        [ -n "$w" ] && echo "warned $w" || echo "accepted"
        return
    fi
    echo "refused $(grep -oE ':[0-9]+:[0-9]+: error' "$OUT/e" | head -1 | cut -d: -f2)"
}
run_zig () {
    [ "$have_zig" = 1 ] || { echo "skipped"; return; }
    if (cd "$OUT" && zig build-obj "$1" >/dev/null 2>"$OUT/e"); then echo "accepted"; return; fi
    echo "refused $(grep -oE '\.zig:[0-9]+:[0-9]+: error' "$OUT/e" | head -1 | cut -d: -f2)"
}

verdict () {   # verdict RESULT EXPECTED_LINE
    case "$1" in
        accepted) printf 'accepted' ;;
        skipped)  printf 'skipped' ;;
        warned*)  local ln=${1#warned }
                  [ "$ln" = "$2" ] && printf 'warned, at the mistake' \
                                   || printf 'warned, at line %s' "${ln:-?}" ;;
        *) local ln=${1#refused }
           if [ "$ln" = "$2" ]; then printf 'refused, at the mistake'
           else printf 'refused, at line %s' "${ln:-?}"; fi ;;
    esac
}

cases=()
if [ $# -gt 0 ]; then for a in "$@"; do cases+=("$HERE/cases/$a.mereo"); done
else for f in "$HERE"/cases/*.mereo; do cases+=("$f"); done; fi

[ "$have_zig" = 1 ] || echo "  (zig not installed -- its column is skipped)"
printf '  %-16s %-26s %-26s %s\n' case mereo "c++ (concepts)" zig
fail=0
for m in "${cases[@]}"; do
    name=$(basename "$m" .mereo)
    cpp="$HERE/cases/$name.cpp"; zig="$HERE/cases/$name.zig"
    cp "$zig" "$OUT/$name.zig" 2>/dev/null
    mr=$(run_mereo "$m");  ml=$(mistake_line "$m")
    cr=$(run_cpp "$cpp");  cl=$(mistake_line "$cpp")
    zr=$(run_zig "$name.zig"); zl=$(mistake_line "$zig")
    printf '  %-16s %-26s %-26s %s\n' "$name" \
           "$(verdict "$mr" "$ml")" "$(verdict "$cr" "$cl")" "$(verdict "$zr" "$zl")"
    # mereo is the one under test: it must refuse, and at the mistake
    case "$mr" in refused" "$ml) ;; *) fail=$((fail+1)) ;; esac
done
echo "---"
[ "$fail" = 0 ] && echo "checking: mereo refuses every case at the mistake" \
                || echo "checking: $fail case(s) mereo did not refuse at the mistake"
exit $((fail > 0))
