static inline __attribute__((always_inline)) long _write(long _fd, long _buf, long _len) {
    long _r;
    __asm__ volatile ("syscall" : "=a"(_r)
        : "a"(1), "D"(_fd), "S"(_buf), "d"(_len) : "rcx", "r11", "memory");
    return _r;
}

static inline __attribute__((always_inline)) long _sigaction(long _sig, long _act) {
    long _r;
    register long _r10 __asm__("r10") = 8;   /* sizeof(sigset_t) */
    __asm__ volatile ("syscall" : "=a"(_r)
        : "a"(13), "D"(_sig), "S"(_act), "d"(0), "r"(_r10)
        : "rcx", "r11", "memory");
    return _r;
}

static inline __attribute__((always_inline)) long _assembly_close(long descriptor) {
    long _r;
    __asm__ volatile ("syscall"
        : [result] "=a" (_r)
        : [number] "a" (3), [descriptor] "D" (descriptor)
        : "rcx", "r11", "memory");
    return _r;
}

static inline __attribute__((always_inline)) __attribute__((noreturn)) void _assembly_exit(long status) {
    __asm__ volatile ("syscall"
        : 
        : [status] "D" (status), [number] "a" (231)
        : "rcx", "r11", "memory");
    __builtin_unreachable();
}

static inline __attribute__((always_inline)) long _assembly_open(long path, long flags, long mode) {
    long _r;
    __asm__ volatile ("syscall"
        : [descriptor] "=a" (_r)
        : [number] "a" (2), [path] "D" (path), [flags] "S" (flags), [mode] "d" (mode)
        : "rcx", "r11", "memory");
    return _r;
}

static inline __attribute__((always_inline)) long _assembly_read(long descriptor, long buffer, long capacity) {
    long _r;
    __asm__ volatile ("syscall"
        : [count] "=a" (_r)
        : [number] "a" (0), [descriptor] "D" (descriptor), [buffer] "S" (buffer), [capacity] "d" (capacity)
        : "rcx", "r11", "memory");
    return _r;
}

static inline __attribute__((always_inline)) long _assembly_write(long descriptor, long buffer, long count) {
    long _r;
    __asm__ volatile ("syscall"
        : [written] "=a" (_r)
        : [number] "a" (1), [descriptor] "D" (descriptor), [buffer] "S" (buffer), [count] "d" (count)
        : "rcx", "r11", "memory");
    return _r;
}

__asm__(
  ".globl mereo_sigstub\n"
  "mereo_sigstub:\n"
  "  orq $0x4002, 296(%rdx)\n"  /* uc_sigmask |= SIGINT|SIGTERM   */
  "  add $8, %rsp\n"            /* drop the unused pretcode slot  */
  "  movl $15, %eax\n"          /* __NR_rt_sigreturn              */
  "  syscall\n"
);
extern void mereo_sigstub(void);

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
    _write(2, (long)_d + _i, 7 - _i);
}

__attribute__((force_align_arg_pointer))
void _start() {
    long capacity = 4096;
    char buffer[4096];
    long count = 0;
    long input_descriptor = 0;
    long output_descriptor = 1;
    long _status = 0;
    long _sink = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    _sigaction(13, (long)_sigign);  /* SIGPIPE */

    long _sigact[4] = { (long)mereo_sigstub, 0x4000004, 0, 0 };
    _sigaction(2, (long)_sigact);   /* SIGINT  */
    _sigaction(15, (long)_sigact);  /* SIGTERM */

    input_descriptor = _assembly_open((long)"lorem_ipsum.txt", 0, 0);
    if (__builtin_expect(!(input_descriptor >= 0), 0)) goto error_1_input;

    count = _assembly_read(input_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_2_read_input;

    _sink = _assembly_write(output_descriptor, (long)buffer, count);
    if (__builtin_expect(!(_sink == count), 0)) goto error_3_write_output;

release_input:
    _assembly_close(input_descriptor);
exit:
    _assembly_exit(_status);
    __builtin_unreachable();

error_1_input:
    if (input_descriptor == -4 || input_descriptor == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    _write(2, (long)"abc: 1: input \"lorem_ipsum.txt\": ", 33);
    _write_value(input_descriptor);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_read_input:
    if (count == -4 || count == -32) goto release_input;   /* -EINTR/EPIPE: graceful shutdown */
    _write(2, (long)"abc: 2: read input: ", 20);
    _write_value(count);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto release_input;

error_3_write_output:
    if (_sink == -4 || _sink == -32) goto release_input;   /* -EINTR/EPIPE: graceful shutdown */
    _write(2, (long)"abc: 3: write output: ", 22);
    _write_value(_sink);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto release_input;
}
