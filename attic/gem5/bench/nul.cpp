#define AI __attribute__((always_inline)) inline
AI long s3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
extern "C" __attribute__((force_align_arg_pointer,externally_visible)) void _start(){ s3(60,0,0,0); __builtin_unreachable(); }
