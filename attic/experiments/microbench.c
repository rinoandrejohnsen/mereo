// Isolates DISPATCH cost: runs each machine's control flow in a hot loop with
// the syscalls stubbed to cheap, sign-opaque values (always success at runtime,
// but the compiler can't prove it, so every branch/indirect-jump stays real).
#define _POSIX_C_SOURCE 199309L
#include <stdio.h>
#include <time.h>

volatile long sink = 0;

// register-launder: forces x to be runtime-unknown (sign can't be folded),
// with ~zero overhead (no memory traffic) — the DoNotOptimize trick.
static inline long opaque(long x){ __asm__("" : "+r"(x)); return x; }
#define OPEN(i)  opaque(3  + ((i) & 7))    // fd     >= 0
#define READ(i)  opaque(28 + ((i) & 31))   // nbytes >= 0
#define WRITE(i) opaque(28 + ((i) & 31))   // nbytes >= 0

// ---- A: linear (simple.c): predicted branches, no indirect jump ----
static long bench_linear(long M){
    long acc = 0;
    for (long i = 0; i < M; i++){
        long code = 1, fd, count, wrote;
        fd = OPEN(i);                if (fd < 0)    goto e;
        code = 2; count = READ(i);   if (count < 0) goto c;
        code = 3; wrote = WRITE(i);  if (wrote < 0) goto c;
        code = 0;
    c:  ;
    e:  acc += code;
    }
    return acc;
}

// ---- B: bytecode dispatch (simple2.c): if-select + double-indirect goto ----
static long bench_bytecode(long M){
    static const unsigned char prog[5] = {0,1,2,3,4};
    long acc = 0;
    for (long i = 0; i < M; i++){
        static const void* dt[5] = {&&init,&&rd,&&wr,&&cl,&&hl};
        long code = 1, r; int state = 0;
        #define DISP() goto *dt[prog[state]]
        DISP();
    init: r = OPEN(i);  state = (r < 0) ? 4 : 1; DISP();
    rd:   code = 2; r = READ(i);  state = (r < 0) ? 3 : 2; DISP();
    wr:   code = 3; r = WRITE(i); if (r > 0) code = 0; state = 3; DISP();
    cl:   state = 4; DISP();
    hl:   acc += code;
        #undef DISP
    }
    return acc;
}

// ---- C: branchless label-pair route: sign-bit single-indirect, no if ----
static long bench_route(long M){
    long acc = 0;
    for (long i = 0; i < M; i++){
        static const void* od[2]={&&rd,&&hl}, *rdd[2]={&&wr,&&cl}, *wd[2]={&&ok,&&cl};
        long code = 1, r;
        r = OPEN(i);  goto *od[(unsigned long)r >> 63];
    rd: code = 2; r = READ(i);  goto *rdd[(unsigned long)r >> 63];
    wr: code = 3; r = WRITE(i); goto *wd[(unsigned long)r >> 63];
    ok: code = 0; goto cl;
    cl: goto hl;
    hl: acc += code;
    }
    return acc;
}

// ---- D: state register + Mealy matrix (fsm.c): branchless matrix + indirect ----
static const unsigned char M_nxt[5][2] = { {1,4},{2,3},{3,3},{4,4},{4,4} };
static const long          M_out[5][2] = { {0,1},{0,2},{0,3},{0,0},{0,0} };
static long bench_fsm(long M){
    long acc = 0;
    for (long i = 0; i < M; i++){
        static const void* h[5] = {&&o,&&rd,&&wr,&&cl,&&hl};
        long code = 0, in, r; int state = 0;
        goto *h[state];
    o:  r = OPEN(i);  in=(unsigned long)r>>63; code=M_out[state][in]; state=M_nxt[state][in]; goto *h[state];
    rd: r = READ(i);  in=(unsigned long)r>>63; code=M_out[state][in]; state=M_nxt[state][in]; goto *h[state];
    wr: r = WRITE(i); in=(unsigned long)r>>63; code=M_out[state][in]; state=M_nxt[state][in]; goto *h[state];
    cl: state=M_nxt[state][0]; goto *h[state];
    hl: acc += code;
    }
    return acc;
}

static double best_ns(long (*f)(long), long M, int trials){
    double best = 1e30;
    for (int t = 0; t < trials; t++){
        struct timespec a,b;
        clock_gettime(CLOCK_MONOTONIC,&a);
        long r = f(M);
        clock_gettime(CLOCK_MONOTONIC,&b);
        sink += r;
        double ns = ((b.tv_sec-a.tv_sec)*1e9 + (b.tv_nsec-a.tv_nsec)) / (double)M;
        if (ns < best) best = ns;
    }
    return best;
}

int main(void){
    long M = 200000000;
    int  T = 7;
    printf("ns per full machine-run  (min of %d trials x %ld runs)\n", T, M);
    printf("  linear   (simple.c, predicted branches)   : %.3f\n", best_ns(bench_linear,   M, T));
    printf("  bytecode (simple2.c, if + 2x indirect)    : %.3f\n", best_ns(bench_bytecode, M, T));
    printf("  route    (branchless sign-bit indirect)   : %.3f\n", best_ns(bench_route,    M, T));
    printf("  fsm      (state reg + Mealy matrix)       : %.3f\n", best_ns(bench_fsm,      M, T));
    return 0;
}
