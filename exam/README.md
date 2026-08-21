# The exam

One program written twice and measured. The report is `docs/exam.md`.

```
exam/
  SPEC.md              what the program does, exactly
  c/loglyze.c          hand-optimised freestanding C (214 lines)
  mereo/loglyze.mereo  the same program in mereo (357 lines)
  tools/reference.py   an independent oracle, written the obvious slow way
  tools/fuzz.py        adversarial input
  tools/gen.py         Common Log Format traffic
  tools/bench2.py      interleaved A/B timing
```

Reproduce:

```sh
python3 tools/gen.py 1000000 42 > data/big.log
gcc -O2 -fwrapv -nostdlib -static -fno-stack-protector \
    -fno-tree-loop-distribute-patterns -fwhole-program -fno-strict-aliasing \
    -fno-asynchronous-unwind-tables -fno-ident -o c/loglyze c/loglyze.c
python3 ../mereoc.py mereo/loglyze.mereo > mereo/loglyze.c
gcc <same flags> -Wl,-T,../mereo.lds -s -o mereo/loglyze mereo/loglyze.c
python3 tools/bench2.py ./c/loglyze ./mereo/loglyze data/big.log 21
```

`data/` holds generated input and is not committed.
