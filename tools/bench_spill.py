#!/usr/bin/env python3
"""Generate bench_spill.c -- locals(registers+stack spill) vs global struct,
with and without a per-iteration memory clobber, swept over register pressure N.

Kernel: N distinct unsigned-long accumulators, each mixed with its neighbour
(v[i] = v[i]*GOLDEN + v[i+1] + t). All N are live across the loop back-edge, so
once N exceeds the usable GPRs the `locals` build must spill. The `global` build
puts the same N values in a static struct's named fields. `clobber` inserts an
empty `asm volatile(...:::"memory")` each iteration -- a free stand-in for a
syscall's memory clobber; `clean` inserts nothing.
"""

MAXN = 1024
NS = [8, 32, 128, 512, 1024]
MULT = "0x9E3779B97F4A7C15UL"   # golden-ratio odd multiplier: no cheap strength reduction


def kernel(storage, clob, n):
    name = f"k_{storage}_{clob}_{n}"
    v = (lambda i: f"g.f{i}") if storage == "global" else (lambda i: f"f{i}")
    out = [f"__attribute__((noinline)) unsigned long {name}"
           "(unsigned long seed, unsigned long iters) {"]
    if storage == "locals":
        out.append("    unsigned long "
                   + ", ".join(f"f{i} = seed + {i}UL" for i in range(n)) + ";")
    else:
        out.append("    " + " ".join(f"g.f{i} = seed + {i}UL;" for i in range(n)))
    out.append("    for (unsigned long t = 0; t < iters; t++) {")
    for i in range(n):
        out.append(f"        {v(i)} = {v(i)} * {MULT} + {v((i + 1) % n)} + t;")
    if clob == "clobber":
        out.append('        __asm__ volatile ("" ::: "memory");')
    out.append("    }")
    out.append("    return " + " ^ ".join(v(i) for i in range(n)) + ";")
    out.append("}")
    return name, "\n".join(out)


def generate():
    fields = ", ".join(f"f{i}" for i in range(MAXN))
    parts = ["#include <stdio.h>", "#include <time.h>", "",
             f"static struct {{ unsigned long {fields}; }} g;", ""]

    names = []
    for storage in ("locals", "global"):
        for clob in ("clean", "clobber"):
            for n in NS:
                nm, code = kernel(storage, clob, n)
                names.append(nm)
                parts.append(code)
                parts.append("")

    parts.append('''typedef unsigned long (*kfn)(unsigned long, unsigned long);

static double bench(kfn fn, unsigned long seed, unsigned long iters,
                    int reps, volatile unsigned long *sink) {
    double best = 1e18;
    for (int r = 0; r < reps; r++) {
        struct timespec a, b;
        clock_gettime(CLOCK_MONOTONIC, &a);
        unsigned long acc = fn(seed, iters);
        clock_gettime(CLOCK_MONOTONIC, &b);
        *sink ^= acc;
        double ns = (b.tv_sec - a.tv_sec) * 1e9 + (b.tv_nsec - a.tv_nsec);
        if (ns < best) best = ns;
    }
    return best / (double)iters;
}
''')

    warm = "\n".join(f"    {nm}(seed, 50000);" for nm in names)

    blocks = []
    for n in NS:
        blocks.append(f'''    {{
        unsigned long it = 200000000UL / {n}UL;
        if (it > 20000000UL) it = 20000000UL;
        if (it < 200000UL)   it = 200000UL;
        double a = bench(k_locals_clean_{n},   seed, it, reps, &sink);
        double b = bench(k_global_clean_{n},   seed, it, reps, &sink);
        double c = bench(k_locals_clobber_{n}, seed, it, reps, &sink);
        double d = bench(k_global_clobber_{n}, seed, it, reps, &sink);
        printf("%5d | %10lu | %9.2f %9.2f | %9.2f %9.2f | %6.2fx %6.2fx\\n",
               {n}, it, a, b, c, d, b / a, d / c);
    }}''')

    parts.append('''int main(int argc, char **argv) {
    unsigned long seed = (unsigned long)argc * 2654435761UL + 1UL;
    int reps = 7;
    volatile unsigned long sink = 0;

''' + warm + '''

    printf("reps=%d  ns per outer iteration (each = N mul-add updates); iters adapts to N\\n", reps);
    printf("clean = no barrier ; clob = asm volatile(\\"\\":::\\"memory\\") once/iteration\\n\\n");
    printf("%5s | %10s | %9s %9s | %9s %9s | %7s %7s\\n",
           "N", "iters", "loc_clean", "glb_clean", "loc_clob", "glb_clob", "g/l cln", "g/l clb");
''' + "\n".join(blocks) + '''
    printf("\\nsink=%lu\\n", sink);
    return 0;
}''')

    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(generate())
