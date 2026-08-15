// Same program shape as pk.cpp, but the record's fields ALREADY align:
// long(8) @0, short(2) @8, short(2) @10, int(4) @12 -> 16 bytes, no padding.
// So `packed` should change nothing at all.
#define AI __attribute__((always_inline)) inline
AI long sys3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r)
  :"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
[[noreturn]] AI void ex(long s){sys3(60,s,0,0);__builtin_unreachable();}
#ifdef PACKED
#  define ATTR __attribute__((packed))
#else
#  define ATTR
#endif
struct ATTR Rec { long value; unsigned short port; unsigned short flags; unsigned int seq; };
#ifndef N
#  define N 4096
#endif
#ifndef PASSES
#  define PASSES 8
#endif
static Rec arr[N];
extern "C" __attribute__((force_align_arg_pointer, externally_visible)) void _start () {
  for (long i = 0; i < N; ++i) { arr[i].value = i*3; arr[i].port=(unsigned short)i; arr[i].flags=(unsigned short)(i>>3); arr[i].seq=(unsigned)i; }
  long acc = 0;
  for (long p = 0; p < PASSES; ++p)
    for (long i = 0; i < N; ++i) { arr[i].value += arr[i].port + p; acc += arr[i].value ^ arr[i].seq ^ arr[i].flags; }
  unsigned char out[1] = { (unsigned char)('0' + (acc & 7)) };
  sys3(1, 1, (long)out, 1); ex(0);
}
