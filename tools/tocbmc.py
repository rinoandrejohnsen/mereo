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

HEAD = re.compile(
    r"static inline __attribute__\(\(always_inline\)\)\s+"
    r"(long|void)\s+(_assembly_\w+|_write|_sigaction|_scan|_same|_mereo_cpu)"
    r"\s*\(([^)]*)\)\s*\{")


def each_primitive(text):
    """Head, params, and the WHOLE body, by counting braces.

    A regex cannot do this: the one-level body pattern reaches a single level of
    nesting and `_same` has two -- an `if` around a `while` -- so it was
    silently left unmodelled while the count said seven of eight. CBMC then
    checked the real byte loop and reported it out of bounds, which took a
    while to recognise as a hole in this file rather than in mereo."""
    out, pos = [], 0
    while True:
        m = HEAD.search(text, pos)
        if not m:
            return out
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        out.append((m.start(), i, m.group(1), m.group(2), m.group(3)))
        pos = i


def model_of(ret, name, params):
    ps = [q.strip().split()[-1].lstrip("*") for q in params.split(",") if q.strip()]
    body = []
    # A model REPLACES a body, so whatever the body checked stops being
    # checked. For the two that read caller memory that would hide the
    # question worth asking, so the obligation is asserted rather than
    # assumed: these say what the caller must have got right, and CBMC
    # reports the caller when it did not.
    if name == "_scan":
        body = ['__CPROVER_assert(_len <= 0 || __CPROVER_r_ok((void *)_pp, '
                '(unsigned long)_len), "scan reads inside its region");',
                "long _o = nondet_long();",
                # its stated promise: `ensure offset <= length`
                "__CPROVER_assume(_o >= 0 && _o <= _len);",
                "return _o;"]
    elif name == "_same":
        body = ['__CPROVER_assert(_pl <= 0 || __CPROVER_r_ok((void *)_pp, '
                '(unsigned long)_pl), "equals reads inside its first region");',
                '__CPROVER_assert(_ql <= 0 || __CPROVER_r_ok((void *)_qq, '
                '(unsigned long)_ql), "equals reads inside its second region");',
                "long _e = nondet_long();",
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


found = each_primitive(src)
for start, end, ret, name, params in reversed(found):
    src = src[:start] + model_of(ret, name, params) + src[end:]
n_wrap = len(found)
# `nondet_long` needs declaring; the __CPROVER_ built-ins must NOT be. A
# declaration turns a built-in into an ordinary undefined function, CBMC says
# "no body for callee __CPROVER_r_ok" and gives it a nondeterministic result --
# so every assertion written with it passed or failed at random, and
# `havoc_slice` quietly did nothing at all. Both were declared here for two
# hours and the checks they were supposed to perform were not being performed.
src = "long nondet_long(void);\n" + src
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
