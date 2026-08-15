static inline __attribute__((always_inline)) long syscall1(long n, long a1) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) long syscall3(long n, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) long syscall4(long n, long a1, long a2, long a3, long a4) {
    long ret;
    register long r10 __asm__("r10") = a4;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3), "r"(r10) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) void memory_fence(void) {
    __asm__ volatile ("mfence"
        : 
        : 
        : "memory");
}

static inline __attribute__((always_inline)) long population_count(long source) {
    long _r;
    __asm__ ("popcnt %[source], %[result]"
        : [result] "=r" (_r)
        : [source] "r" (source)
        : );
    return _r;
}

static inline __attribute__((always_inline)) void _write_value(long _e) {
    char _d[8];
    long _n = _e < 0;
    long _i;
    if (_n) _e = -_e;
    _d[1] = '0' + _e / 10000 % 10;
    _d[2] = '0' + _e / 1000 % 10;
    _d[3] = '0' + _e / 100 % 10;
    _d[4] = '0' + _e / 10 % 10;
    _d[5] = '0' + _e % 10;
    _d[6] = '\n';
    _i = 5 - (_e >= 10) - (_e >= 100) - (_e >= 1000) - (_e >= 10000);
    _d[_i - 1] = '-';
    _i = _i - _n;
    syscall3(1, 2, (long)_d + _i, 7 - _i);
}

__attribute__((force_align_arg_pointer))
void _start() {
    long bits = 0;
    long cpu_value = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    bits = population_count(255);
    if (__builtin_expect(!(bits >= 0), 0)) goto error_1_count_cpu;

    memory_fence();

exit:
    syscall1(231, bits);
    __builtin_unreachable();

error_1_count_cpu:
    if (bits == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"bits: 1: count cpu: ", 20);
    _write_value(bits);
    bits = 1;
    __asm__("# stage 1" : "+r"(bits));
    goto exit;
}
