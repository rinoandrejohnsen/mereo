#!/usr/bin/env python3
"""mereo's C, as CBMC can check it.

CBMC is bit-precise and answers with a COUNTEREXAMPLE rather than an alarm,
which is the half Eva cannot do and the half that matters when the question is
"can this index reach past the end". What it cannot do is inline assembly: the
syscall wrappers and the two C helpers become opaque, every value downstream
goes nondeterministic, and the SAT instance stops being solvable.

So each one is replaced by a MODEL of what it promises -- which mereo already
declares, port by port, in linux.mereo and core.mereo:

    read     writes at most `capacity` bytes and answers how many
    write    reads `count` bytes and answers how many it took
    _scan    answers an offset no greater than the length it was given
    _same    answers 0 or 1

The buffer is havoc'd rather than left alone, so the parse explores real
inputs instead of the zeros a static would otherwise hold.
"""
import re
import sys

src = open(sys.argv[1]).read()

# a promise is already an assumption; CBMC takes it as one
src, n_as = re.subn(r"__attribute__\s*\(\(\s*__assume__\s*\((.*)\)\s*\)\)\s*;",
                    lambda m: "__CPROVER_assume(%s);" % m.group(1).strip(), src)
src = re.sub(r"__attribute__\s*\(\(\s*(externally_visible|noreturn|naked)\s*\)\)",
             "", src)

WRAP = re.compile(
    r"static inline __attribute__\(\(always_inline\)\)\s+"
    r"(long|void)\s+(_assembly_\w+|_write|_sigaction|_scan|_same|_mereo_cpu)"
    r"\s*\(([^)]*)\)\s*\{(?:[^{}]|\{[^{}]*\})*\}", re.S)


def model(m):
    ret, name, params = m.group(1), m.group(2), m.group(3)
    ps = [q.strip().split()[-1].lstrip("*") for q in params.split(",") if q.strip()]
    body = []
    if name == "_scan":
        # its stated promise: `ensure offset <= length`
        body = ["long _o = nondet_long();",
                "__CPROVER_assume(_o >= 0 && _o <= _len);",
                "return _o;"]
    elif name == "_same":
        body = ["long _e = nondet_long();",
                "__CPROVER_assume(_e == 0 || _e == 1);",
                "return _e;"]
    elif "buffer" in ps and "capacity" in ps:
        body = ["long _n = nondet_long();",
                "__CPROVER_assume(_n >= -1 && _n <= capacity);",
                "if (_n > 0) __CPROVER_havoc_slice((void *)buffer, (unsigned long)_n);",
                "return _n;"]
    elif "buffer" in ps and "count" in ps:
        body = ["long _n = nondet_long();",
                "__CPROVER_assume(_n >= -1 && _n <= count);",
                "return _n;"]
    elif ret == "void":
        body = ["return;"]
    else:
        body = ["return nondet_long();"]
    return ("%s %s(%s) {\n    %s\n}" % (ret, name, params, "\n    ".join(body)))


src, n_wrap = WRAP.subn(model, src)
src = ("long nondet_long(void);\n"
       "void __CPROVER_havoc_slice(void *, unsigned long);\n" + src)
sys.stderr.write("  promises -> assumptions: %d   primitives modelled: %d\n"
                 % (n_as, n_wrap))
open(sys.argv[2], "w").write(src)

# Usage:
#   python3 mereoc.py PROG.mereo > p.c
#   python3 tools/tocbmc.py p.c p_cbmc.c
#   cbmc --function _start --unwind N --unwinding-assertions \
#        --bounds-check --pointer-check --signed-overflow-check p_cbmc.c
#
# `--unwinding-assertions` is the part that makes the answer mean something:
# without it a loop that needed more than N turns is simply cut, and the
# report is "no failure within N", not "no failure".
