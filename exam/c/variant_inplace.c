/* loglyze -- summarise NCSA Common Log Format. See exam/SPEC.md.
 *
 * Written the way this kind of thing is written when it has to be fast and
 * has to be right: no allocation, one buffer, one pass, and every bound
 * stated where the storage is declared.
 *
 * Two builds from one source. Freestanding (default) talks to the kernel
 * directly and is what gets benchmarked; -DHOSTED uses libc read/write so the
 * sanitizers and valgrind have something to hold on to. The parsing is the
 * same code either way -- the shim is four lines at the top.
 */

#define LINE_MAX_   8192
#define PATH_MAX_   255
#define TABLE_BITS  13                    /* 8192 slots for 4096 live paths:
                                             a half-full table probes short */
#define TABLE_SLOTS (1u << TABLE_BITS)
#define TABLE_MAX   4096
#define ARENA_MAX   (1u << 20)
#define READ_BUF    (64u << 10)
#define TOP_N       10

typedef unsigned long  u64;
typedef unsigned int   u32;
typedef unsigned char  u8;

#ifdef HOSTED
#include <unistd.h>
static long io_read(int fd, void *p, unsigned long n)  { return read(fd, p, n); }
static long io_write(int fd, const void *p, unsigned long n) { return write(fd, p, n); }
#else
static inline long sys3(long nr, long a, long b, long c) {
    long r;
    __asm__ volatile ("syscall" : "=a"(r) : "a"(nr), "D"(a), "S"(b), "d"(c)
                      : "rcx", "r11", "memory");
    return r;
}
static long io_read(int fd, void *p, unsigned long n)  { return sys3(0, fd, (long)p, (long)n); }
static long io_write(int fd, const void *p, unsigned long n) { return sys3(1, fd, (long)p, (long)n); }
__attribute__((noreturn)) static void io_exit(int code) {
    __asm__ volatile ("syscall" :: "a"(231), "D"((long)code) : "memory");
    __builtin_unreachable();
}
#endif

/* ---------------------------------------------------------------- storage */
static u8   line[LINE_MAX_];
static u8   rbuf[READ_BUF];
static u8   arena[ARENA_MAX];
static u32  arena_used;

static struct { u32 hash, off, len, count, seq; } slot[TABLE_SLOTS];
static u32  live;

static u64  requests, total_bytes, malformed;
static u64  klass[5];

/* ------------------------------------------------------------------ parse */
static inline int is_space(u8 c) {
    return c == ' ' || c == '\t' || c == '\r' || c == '\v' || c == '\f';
}

/* FNV-1a: short keys, no table, and the multiply is one instruction. */
static inline u32 hash_of(const u8 *p, u32 n) {
    u32 h = 2166136261u;
    for (u32 i = 0; i < n; i++) { h ^= p[i]; h *= 16777619u; }
    return h;
}

static void intern(const u8 *p, u32 n) {
    u32 h = hash_of(p, n);
    u32 i = h & (TABLE_SLOTS - 1);
    for (;;) {
        if (slot[i].count == 0) break;
        if (slot[i].hash == h && slot[i].len == n) {
            const u8 *q = arena + slot[i].off;
            u32 k = 0;
            while (k < n && q[k] == p[k]) k++;
            if (k == n) { slot[i].count++; return; }
        }
        i = (i + 1) & (TABLE_SLOTS - 1);
    }
    if (live >= TABLE_MAX || arena_used + n > ARENA_MAX) return;
    for (u32 k = 0; k < n; k++) arena[arena_used + k] = p[k];
    slot[i].hash = h; slot[i].off = arena_used; slot[i].len = n;
    slot[i].count = 1; slot[i].seq = live;
    arena_used += n; live++;
}

/* one line, already truncated to LINE_MAX_ and with no newline in it */
static void do_line(const u8 *s, u32 n) {
    u32 q1 = 0;
    while (q1 < n && s[q1] != '"') q1++;
    if (q1 == n) { malformed++; return; }
    u32 q2 = q1 + 1;
    while (q2 < n && s[q2] != '"') q2++;
    if (q2 == n) { malformed++; return; }

    /* inside the quotes: METHOD SP PATH [SP VERSION] */
    u32 a = q1 + 1;
    u32 sp = a;
    while (sp < q2 && s[sp] != ' ') sp++;
    if (sp == q2) { malformed++; return; }
    u32 ps = sp + 1, pe = ps;
    while (pe < q2 && s[pe] != ' ') pe++;
    u32 plen = pe - ps;
    if (plen == 0 || plen > PATH_MAX_) { malformed++; return; }

    /* after the quotes: STATUS BYTES */
    u32 t = q2 + 1;
    while (t < n && is_space(s[t])) t++;
    u32 st_s = t;
    while (t < n && !is_space(s[t])) t++;
    u32 st_n = t - st_s;
    while (t < n && is_space(s[t])) t++;
    u32 by_s = t;
    while (t < n && !is_space(s[t])) t++;
    u32 by_n = t - by_s;
    if (st_n == 0 || by_n == 0) { malformed++; return; }
    if (st_n != 3) { malformed++; return; }
    for (u32 i = 0; i < 3; i++)
        if (s[st_s + i] < '0' || s[st_s + i] > '9') { malformed++; return; }

    u64 nb = 0;
    if (by_n == 1 && s[by_s] == '-') {
        nb = 0;
    } else {
        for (u32 i = 0; i < by_n; i++) {
            u8 c = s[by_s + i];
            if (c < '0' || c > '9') { malformed++; return; }
            nb = nb * 10 + (u64)(c - '0');
        }
    }

    requests++;
    total_bytes += nb;
    u32 c = (u32)(s[st_s] - '0');
    if (c >= 1 && c <= 5) klass[c - 1]++;
    intern(s + ps, plen);
}

/* ----------------------------------------------------------------- output */
static u8  obuf[1 << 16];
static u32 olen;

static void emit(const u8 *p, u32 n) {
    for (u32 i = 0; i < n; i++) obuf[olen++] = p[i];
}
static void emit_lit(const char *s) {
    const u8 *p = (const u8 *)s;
    u32 n = 0; while (p[n]) n++;
    emit(p, n);
}
static void emit_u64(u64 v) {
    u8 tmp[20]; u32 k = 0;
    if (v == 0) tmp[k++] = '0';
    while (v) { tmp[k++] = (u8)('0' + v % 10); v /= 10; }
    while (k) obuf[olen++] = tmp[--k];
}

static void report(void) {
    static const char *names[5] = {"1xx ", "2xx ", "3xx ", "4xx ", "5xx "};
    emit_lit("requests ");  emit_u64(requests);    emit_lit("\n");
    emit_lit("bytes ");     emit_u64(total_bytes); emit_lit("\n");
    emit_lit("malformed "); emit_u64(malformed);   emit_lit("\n");
    for (u32 i = 0; i < 5; i++) { emit_lit(names[i]); emit_u64(klass[i]); emit_lit("\n"); }
    emit_lit("top\n");

    /* Ten winners out of at most 4096: a full selection sort would be 4096
       passes, so take ten passes instead and mark what has been taken. */
    static u8 taken[TABLE_SLOTS];
    for (u32 r = 0; r < TOP_N; r++) {
        u32 best = TABLE_SLOTS;
        for (u32 i = 0; i < TABLE_SLOTS; i++) {
            if (!slot[i].count || taken[i]) continue;
            if (best == TABLE_SLOTS
                || slot[i].count > slot[best].count
                || (slot[i].count == slot[best].count && slot[i].seq < slot[best].seq))
                best = i;
        }
        if (best == TABLE_SLOTS) break;
        taken[best] = 1;
        emit_u64(slot[best].count);
        emit_lit(" ");
        emit(arena + slot[best].off, slot[best].len);
        emit_lit("\n");
    }
    for (u32 done = 0; done < olen; ) {
        long w = io_write(1, obuf + done, olen - done);
        if (w <= 0) break;
        done += (u32)w;
    }
}

/* ------------------------------------------------------------------- main */
static void run(void) {
    u32 held = 0;          /* bytes of a straddling line already in `line` */
    int over = 0;          /* this line ran past LINE_MAX_: drop to newline */
    for (;;) {
        long got = io_read(0, rbuf, READ_BUF);
        if (got <= 0) break;
        u32 n = (u32)got, i = 0;
        while (i < n) {
            u32 j = i;
            while (j < n && rbuf[j] != '\n') j++;
            u32 chunk = j - i;
            /* The common case by far: a whole line sitting inside this read,
               with nothing held over. Parse it where it lies -- copying it to
               `line` first would touch every byte of the input twice. */
            if (held == 0 && !over && j < n) {
                do_line(rbuf + i, chunk < LINE_MAX_ ? chunk : LINE_MAX_);
                i = j + 1;
                continue;
            }
            if (!over) {
                u32 room = LINE_MAX_ - held;
                u32 take = chunk < room ? chunk : room;
                for (u32 k = 0; k < take; k++) line[held + k] = rbuf[i + k];
                held += take;
                if (take < chunk) over = 1;
            }
            if (j < n) {                       /* the newline is in this read */
                do_line(line, held);
                held = 0; over = 0;
                i = j + 1;
            } else {
                i = n;
            }
        }
    }
    if (held) do_line(line, held);
    report();
}

#ifdef HOSTED
int main(void) { run(); return 0; }
#else
__attribute__((force_align_arg_pointer, externally_visible))
void _start(void) { run(); io_exit(0); }
#endif
