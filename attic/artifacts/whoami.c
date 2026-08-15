static inline __attribute__((always_inline)) long syscall0(long n) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n) : "rcx", "r11", "memory");
    return ret;
}

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

static inline __attribute__((always_inline)) long _decimal(long _n, long _op) {
    char *_o = (char *)_op;
    char _t[20];
    long _i = 0, _j = 0;
    if (_n == 0) { _o[0] = (char)48; return 1; }
    while (_n > 0) { _t[_i++] = (char)(48 + _n % 10); _n /= 10; }
    while (_i > 0) _o[_j++] = _t[--_i];
    return _j;
}

static inline __attribute__((always_inline)) long _same(long _pp, long _pl, long _qq, long _ql) {
    if (_pl != _ql) return 0;
    char *_p = (char *)_pp, *_q = (char *)_qq;
    long _i = 0;
    while (_i < _pl && _p[_i] == _q[_i]) _i++;
    return _i == _pl;
}

static inline __attribute__((always_inline)) long _scan(long _pp, long _len, long _b) {
    char *_p = (char *)_pp;
    long _i = 0;
    while (_i < _len && (long)(unsigned char)_p[_i] != _b) _i++;
    return _i;
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
    long uid = 0;
    long name_ptr = 0;
    long name_len = 0;
    long written = 0;
    long output_descriptor = 1;
    long getpwuid_1_capacity = 65536;
    char getpwuid_1_buffer[65536];
    long getpwuid_1_count = 0;
    char getpwuid_1_key[16];
    long getpwuid_1_keylen = 0;
    long getpwuid_1_key_ptr = 0;
    long getpwuid_1_cur = 0;
    long getpwuid_1_left = 0;
    long getpwuid_1_name_ptr = 0;
    long getpwuid_1_name_len = 0;
    long getpwuid_1_skip_len = 0;
    long getpwuid_1_uid_len = 0;
    long getpwuid_1_line_len = 0;
    long getpwuid_1_match = 0;
    long getpwuid_1_hits = 0;
    long getpwuid_1_answer_ptr = 0;
    long getpwuid_1_answer_len = 0;
    long getpwuid_1_d = 0;
    long getpwuid_1_e = 0;
    long getpwuid_1_passwd_descriptor = -1;
    long _status = 0;

    long _sigign[4] = { 1, 0, 0, 0 };  /* SIG_IGN */
    syscall4(13, 13, (long)_sigign, 0, 8);  /* SIGPIPE */

    long _sigact[4] = { (long)mereo_sigstub, 0x4000004, 0, 0 };
    syscall4(13, 2, (long)_sigact, 0, 8);   /* SIGINT  */
    syscall4(13, 15, (long)_sigact, 0, 8);  /* SIGTERM */

    uid = syscall0(107);

    getpwuid_1_capacity = 65536;

    getpwuid_1_count = 0;

    getpwuid_1_keylen = 0;

    getpwuid_1_key_ptr = 0;

    getpwuid_1_cur = 0;

    getpwuid_1_left = 0;

    getpwuid_1_name_ptr = 0;

    getpwuid_1_name_len = 0;

    getpwuid_1_skip_len = 0;

    getpwuid_1_uid_len = 0;

    getpwuid_1_line_len = 0;

    getpwuid_1_match = 0;

    getpwuid_1_hits = 0;

    getpwuid_1_answer_ptr = 0;

    getpwuid_1_answer_len = 0;

    getpwuid_1_d = 0;

    getpwuid_1_e = 0;

    getpwuid_1_passwd_descriptor = syscall3(2, (long)"/etc/passwd", 0, 0);
    if (__builtin_expect(!(getpwuid_1_passwd_descriptor >= 0), 0)) goto error_1_getpwuid_1_passwd;

    getpwuid_1_count = syscall3(0, getpwuid_1_passwd_descriptor, (long)getpwuid_1_buffer, getpwuid_1_capacity);
    if (__builtin_expect(!(getpwuid_1_count >= 0), 0)) goto error_2_read_getpwuid_1_passwd;

    getpwuid_1_keylen = _decimal(uid, (long)getpwuid_1_key);

    getpwuid_1_key_ptr = (long)getpwuid_1_key;

    getpwuid_1_cur = (long)getpwuid_1_buffer;

    getpwuid_1_left = getpwuid_1_count;

getpwuid_1_lines:

    getpwuid_1_name_ptr = getpwuid_1_cur;

    getpwuid_1_name_len = _scan(getpwuid_1_cur, getpwuid_1_left, 58);

    getpwuid_1_cur = (getpwuid_1_cur + getpwuid_1_name_len);

    getpwuid_1_cur = (getpwuid_1_cur + 1);

    getpwuid_1_left = (getpwuid_1_left - getpwuid_1_name_len);

    getpwuid_1_left = (getpwuid_1_left - 1);

    getpwuid_1_skip_len = _scan(getpwuid_1_cur, getpwuid_1_left, 58);

    getpwuid_1_cur = (getpwuid_1_cur + getpwuid_1_skip_len);

    getpwuid_1_cur = (getpwuid_1_cur + 1);

    getpwuid_1_left = (getpwuid_1_left - getpwuid_1_skip_len);

    getpwuid_1_left = (getpwuid_1_left - 1);

    getpwuid_1_uid_len = _scan(getpwuid_1_cur, getpwuid_1_left, 58);

    getpwuid_1_match = _same(getpwuid_1_cur, getpwuid_1_uid_len, getpwuid_1_key_ptr, getpwuid_1_keylen);

    getpwuid_1_d = (getpwuid_1_name_ptr - getpwuid_1_answer_ptr);

    getpwuid_1_d = (getpwuid_1_d * getpwuid_1_match);

    getpwuid_1_answer_ptr = (getpwuid_1_answer_ptr + getpwuid_1_d);

    getpwuid_1_e = (getpwuid_1_name_len - getpwuid_1_answer_len);

    getpwuid_1_e = (getpwuid_1_e * getpwuid_1_match);

    getpwuid_1_answer_len = (getpwuid_1_answer_len + getpwuid_1_e);

    getpwuid_1_hits = (getpwuid_1_hits + getpwuid_1_match);

    getpwuid_1_line_len = _scan(getpwuid_1_cur, getpwuid_1_left, 10);

    getpwuid_1_cur = (getpwuid_1_cur + getpwuid_1_line_len);

    getpwuid_1_cur = (getpwuid_1_cur + 1);

    getpwuid_1_left = (getpwuid_1_left - getpwuid_1_line_len);

    getpwuid_1_left = (getpwuid_1_left - 1);

    if (getpwuid_1_left > 0) goto getpwuid_1_lines;

    if (__builtin_expect(!(getpwuid_1_hits >= 1), 0)) goto error_3_getpwuid;

    name_ptr = getpwuid_1_answer_ptr;

    name_len = getpwuid_1_answer_len;

    syscall1(3, getpwuid_1_passwd_descriptor);

    written = syscall3(1, output_descriptor, name_ptr, name_len);
    if (__builtin_expect(!(written == name_len), 0)) goto error_4_write_output;

    written = syscall3(1, output_descriptor, (long)"\n", 1);
    if (__builtin_expect(!(written == 1), 0)) goto error_5_write_output;

    goto exit;
release_getpwuid_1_passwd:
    syscall1(3, getpwuid_1_passwd_descriptor);
exit:
    syscall1(231, _status);
    __builtin_unreachable();

error_1_getpwuid_1_passwd:
    if (getpwuid_1_passwd_descriptor == -4 || getpwuid_1_passwd_descriptor == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"whoami: 1: getpwuid_1_passwd \"/etc/passwd\": ", 44);
    _write_value(getpwuid_1_passwd_descriptor);
    _status = 1;
    __asm__("# stage 1" : "+r"(_status));
    goto exit;

error_2_read_getpwuid_1_passwd:
    if (getpwuid_1_count == -4 || getpwuid_1_count == -32) goto release_getpwuid_1_passwd;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"whoami: 2: read getpwuid_1_passwd: ", 35);
    _write_value(getpwuid_1_count);
    _status = 1;
    __asm__("# stage 2" : "+r"(_status));
    goto release_getpwuid_1_passwd;

error_3_getpwuid:
    if (getpwuid_1_hits == -4 || getpwuid_1_hits == -32) goto release_getpwuid_1_passwd;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"whoami: 3: getpwuid: ", 21);
    _write_value(getpwuid_1_hits);
    _status = 1;
    __asm__("# stage 3" : "+r"(_status));
    goto release_getpwuid_1_passwd;

error_4_write_output:
    if (written == -4 || written == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"whoami: 4: write output: ", 25);
    _write_value(written);
    _status = 1;
    __asm__("# stage 4" : "+r"(_status));
    goto exit;

error_5_write_output:
    if (written == -4 || written == -32) goto exit;   /* -EINTR/EPIPE: graceful shutdown */
    syscall3(1, 2, (long)"whoami: 5: write output \"\\n\": ", 30);
    _write_value(written);
    _status = 1;
    __asm__("# stage 5" : "+r"(_status));
    goto exit;
}
