// Identical program twice; only PACKED differs. A record with mixed field
// widths: naturally laid out it pads to 24 bytes (value 8-aligned at offset 8);
// packed it is 11 bytes (value at offset 1, so every access is misaligned and
// records straddle cache lines).
#define AI __attribute__((always_inline)) inline
AI long sys3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r)
  :"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
[[noreturn]] AI void ex(long s){sys3(60,s,0,0);__builtin_unreachable();}

#ifdef PACKED
#  define ATTR __attribute__((packed))
#else
#  define ATTR
#endif
struct ATTR Rec { unsigned char tag; long value; unsigned short port; };

#ifndef N
#  define N 4096
#endif
#ifndef PASSES
#  define PASSES 8
#endif
static Rec arr[N];

extern "C" __attribute__((force_align_arg_pointer, externally_visible)) void _start () {
  for (long i = 0; i < N; ++i) { arr[i].tag = (unsigned char)i; arr[i].value = i * 3; arr[i].port = (unsigned short)i; }
  long acc = 0;
  for (long p = 0; p < PASSES; ++p)
    for (long i = 0; i < N; ++i) { arr[i].value += arr[i].tag + p; acc += arr[i].value ^ arr[i].port; }
  unsigned char out[1] = { (unsigned char)('0' + (acc & 7)) };
  sys3(1, 1, (long)out, 1);
  ex(0);
}
