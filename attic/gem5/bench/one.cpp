// ONE struct, hammered. No array, so packing changes NO footprint -- it only
// moves `v` from offset 8 (aligned) to offset 1 (misaligned). Pure penalty.
#define AI __attribute__((always_inline)) inline
AI long sys3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r)
  :"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
[[noreturn]] AI void ex(long s){sys3(60,s,0,0);__builtin_unreachable();}
#ifdef PACKED
#  define ATTR __attribute__((packed))
#else
#  define ATTR
#endif
struct ATTR Rec { char t; long v; short p; };
static volatile Rec r;               // volatile: every access is a real load/store
extern "C" __attribute__((force_align_arg_pointer, externally_visible)) void _start () {
  r.t = 1; r.v = 0; r.p = 3;
  for (long i = 0; i < 2000000; ++i) r.v = r.v + 1;
  unsigned char o[1] = { (unsigned char)('0' + (r.v & 7)) };
  sys3(1, 1, (long)o, 1); ex(0);
}
