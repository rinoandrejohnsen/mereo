// fall-through happy path + cold exception handlers (the "TRY" design)
static inline long sc1(long n, long a1){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory");return r;}
static inline long sc2(long n, long a1, long a2){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory");return r;}
static inline long sc3(long n, long a1, long a2, long a3){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory");return r;}

#define TRY(dst, expr, handler) dst = (expr); if (__builtin_expect((dst) < 0, 0)) goto handler

void _start(void) {
    long code, fd, count, wrote;
    char buffer[4096];

    TRY(fd,    sc2(2, (long)"lorem_ipsum.txt", 0),      throw_open);
    TRY(count, sc3(0, fd, (long)buffer, sizeof buffer), throw_read);
    TRY(wrote, sc3(1, 1, (long)buffer, count),          throw_write);
    code = 0;

unwind_close:
    sc1(3, fd);
unwind_exit:
    sc1(60, code);
    __builtin_unreachable();

throw_write: code = 3; goto unwind_close;
throw_read:  code = 2; goto unwind_close;
throw_open:  code = 1; goto unwind_exit;
}
