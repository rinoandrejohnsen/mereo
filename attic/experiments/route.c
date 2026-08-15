// branchless dispatch: route on the sign bit of each syscall result
static inline long sc1(long n, long a1){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1):"rcx","r11","memory");return r;}
static inline long sc2(long n, long a1, long a2){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2):"rcx","r11","memory");return r;}
static inline long sc3(long n, long a1, long a2, long a3){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a1),"S"(a2),"d"(a3):"rcx","r11","memory");return r;}

#define ROUTE(ret, disp) goto *disp[(unsigned long)(ret) >> 63]

void _start(void) {
    long fd, count, code;
    char buffer[4096];
    static const void* open_disp[2]  = { &&do_read,  &&do_halt  };
    static const void* read_disp[2]  = { &&do_write, &&do_close };
    static const void* write_disp[2] = { &&do_ok,    &&do_close };

do_open:
    code  = 1;
    fd    = sc2(2, (long)"lorem_ipsum.txt", 0);
    ROUTE(fd, open_disp);
do_read:
    code  = 2;
    count = sc3(0, fd, (long)buffer, sizeof buffer);
    ROUTE(count, read_disp);
do_write:
    code  = 3;
    ROUTE(sc3(1, 1, (long)buffer, count), write_disp);
do_ok:
    code  = 0;
    goto do_close;
do_close:
    sc1(3, fd);
    goto do_halt;
do_halt:
    sc1(60, code);
    __builtin_unreachable();
}
