static inline __attribute__((always_inline)) long syscall1(long n, long a1) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1) : "rcx", "r11", "memory");
    return ret;
}

static inline __attribute__((always_inline)) long syscall2(long n, long a1, long a2) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2) : "rcx", "r11", "memory");
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
    syscall3(1, 2, (long)_d + _i, 7 - _i);
}

__attribute__((force_align_arg_pointer))
void _start() {
    long capacity = 4096;
    char buffer[4096];
    long count = 0;
    long written = 0;
    long peer = -1;
    long terminal_descriptor = 1;
    long server_descriptor = -1;
    long server_status = 0;
    long client_descriptor = -1;
    long client_status = 0;
    long _status = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    long _sigact[4] = { (long)mereo_sigstub, 0x4000004, 0, 0 };
    syscall4(13, 2, (long)_sigact, 0, 8);   /* SIGINT  */
    syscall4(13, 15, (long)_sigact, 0, 8);  /* SIGTERM */

    server_descriptor = syscall3(41, 2, 1, 0);
    if (__builtin_expect(!(server_descriptor >= 0), 0)) goto error_1_server;

    server_status = syscall3(49, server_descriptor, (long)"\x02\x00\x30\x3a\x7f\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00", 16);
    if (__builtin_expect(!(server_status >= 0), 0)) goto error_2_bind_server;

    server_status = syscall2(50, server_descriptor, 1);
    if (__builtin_expect(!(server_status >= 0), 0)) goto error_3_listen_server;

serve:

    peer = syscall3(43, server_descriptor, 0, 0);
    if (__builtin_expect(!(peer >= 0), 0)) goto error_4_accept_server;

    client_descriptor = peer;

    count = syscall3(0, client_descriptor, (long)buffer, capacity);
    if (__builtin_expect(!(count >= 0), 0)) goto error_5_read_client;

    written = syscall3(1, terminal_descriptor, (long)buffer, count);
    if (__builtin_expect(!(written == count), 0)) goto error_6_write_terminal;

    syscall1(3, client_descriptor);
    goto serve;

    goto release_server;
release_client:
    syscall1(3, client_descriptor);
release_server:
    syscall1(3, server_descriptor);
exit:
    syscall1(231, _status);
    __builtin_unreachable();

error_1_server:
    if (server_descriptor == -4 || server_descriptor == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 1: server: ", 19);
    _write_value(server_descriptor);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_bind_server:
    if (server_status == -4 || server_status == -32) goto release_server;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 2: bind server \"\\x02\\x00\\x30\\x3a\\x7f\\x00\\x00\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\": ", 91);
    _write_value(server_status);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto release_server;

error_3_listen_server:
    if (server_status == -4 || server_status == -32) goto release_server;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 3: listen server: ", 26);
    _write_value(server_status);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto release_server;

error_4_accept_server:
    if (peer == -4 || peer == -32) goto release_server;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 4: accept server: ", 26);
    _write_value(peer);
    _status = 1;
    __asm__("# stage 4" : "+r"(_status));
    goto release_server;

error_5_read_client:
    if (count == -4 || count == -32) goto release_client;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 5: read client: ", 24);
    _write_value(count);
    _status = 1;
    __asm__("# stage 5" : "+r"(_status));
    goto release_client;

error_6_write_terminal:
    if (written == -4 || written == -32) goto release_client;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"server: 6: write terminal: ", 27);
    _write_value(written);
    _status = 1;
    __asm__("# stage 6" : "+r"(_status));
    goto release_client;
}
