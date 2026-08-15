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

static inline __attribute__((always_inline)) long _scan(long _pp, long _len, long _b) {
    char *_p = (char *)_pp;
    long _i = 0;
    while (_i < _len && (long)(unsigned char)_p[_i] != _b) _i++;
    return _i;
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

void _run(long _entry);

__attribute__((naked)) void _start(void) {
    __asm__(
        "mov %rsp, %rdi\n"       /* entry pointer (-> argc) */
        "jmp _run\n"
    );
}

__attribute__((force_align_arg_pointer))
void _run(long _entry) {
    long argc = 0;
    long arg = 0;
    long len = 0;
    long pos = 0;
    long rem = 0;
    long off = 0;
    long keep = 0;
    long d = 0;
    long e = 0;
    long comp_start = 0;
    long comp_len = 0;
    long out_ptr = 0;
    long written = 0;
    long output_descriptor = 1;
    long _status = 0;

    long _argc = *(long *)_entry;
    char **_argv = (char **)(_entry + 8);

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    argc = _argc;

    if (__builtin_expect(!(argc >= 2), 0)) goto error_1_argc;

    arg = (long)_argv[1];

    len = _scan(arg, 4096, 0);

walk:

    rem = (len - pos);

    off = _scan((arg + pos), rem, 47);

    keep = (off + 1);

    keep = (1 / keep);

    keep = (1 - keep);

    d = (pos - comp_start);

    d = (d * keep);

    comp_start = (comp_start + d);

    e = (off - comp_len);

    e = (e * keep);

    comp_len = (comp_len + e);

    pos = (pos + off);

    pos = (pos + 1);

    if (pos < len) goto walk;

    out_ptr = (arg + comp_start);

    if (__builtin_expect(len == 0, 0)) goto name_road_0;
    if (__builtin_expect(comp_len == 0, 0)) goto name_road_1;

    written = syscall3(1, output_descriptor, out_ptr, comp_len);
    if (__builtin_expect(!(written == comp_len), 0)) goto error_2_write_output;

    written = syscall3(1, output_descriptor, (long)"\n", 1);
    if (__builtin_expect(!(written == 1), 0)) goto error_3_write_output;

name:

exit:
    syscall1(231, _status);
    __builtin_unreachable();

name_road_0:
    written = syscall3(1, output_descriptor, (long)"\n", 1);
    if (__builtin_expect(!(written == 1), 0)) goto error_4_write_output;
    goto name;

name_road_1:
    written = syscall3(1, output_descriptor, (long)"/", 1);
    if (__builtin_expect(!(written == 1), 0)) goto error_5_write_output;
    written = syscall3(1, output_descriptor, (long)"\n", 1);
    if (__builtin_expect(!(written == 1), 0)) goto error_6_write_output;
    goto name;

error_1_argc:
    if (argc == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 1: argc: ", 19);
    _write_value(argc);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_write_output:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 2: write output: ", 27);
    _write_value(written);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto exit;

error_3_write_output:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 3: write output \"\\n\": ", 32);
    _write_value(written);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto exit;

error_4_write_output:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 4: write output \"\\n\": ", 32);
    _write_value(written);
    _status = 1;
    __asm__("# stage 4" : "+r"(_status));
    goto exit;

error_5_write_output:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 5: write output \"/\": ", 31);
    _write_value(written);
    _status = 1;
    __asm__("# stage 5" : "+r"(_status));
    goto exit;

error_6_write_output:
    if (written == -32) goto exit;   /* -EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"basename: 6: write output \"\\n\": ", 32);
    _write_value(written);
    _status = 1;
    __asm__("# stage 6" : "+r"(_status));
    goto exit;
}
