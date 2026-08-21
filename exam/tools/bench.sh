#!/usr/bin/env bash
# bench.sh PROG FILE RUNS -- best wall-clock of RUNS, in ms
prog=$1; file=$2; runs=${3:-5}
best=999999
for _ in $(seq "$runs"); do
    s=$(date +%s%N)
    "$prog" < "$file" > /dev/null
    e=$(date +%s%N)
    ms=$(( (e - s) / 1000000 ))
    [ "$ms" -lt "$best" ] && best=$ms
done
echo "$best"
