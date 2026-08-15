// A loop GCC WANTS to vectorise: sum one field across an array of records.
#define AI __attribute__((always_inline)) inline
AI long sys3(long n,long a,long b,long c){long r;__asm__ volatile("syscall":"=a"(r)
  :"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}
[[noreturn]] AI void ex(long s){sys3(60,s,0,0);__builtin_unreachable();}
#ifdef PACKED
#  define ATTR __attribute__((packed))
#else
#  define ATTR
#endif
struct ATTR Rec { long v; char t; };     // normal 16B (7 pad), packed 9B
static Rec arr[8192];
extern "C" __attribute__((force_align_arg_pointer, externally_visible)) void _start () {
  for (long i=0;i<8192;++i){ arr[i].v=i; arr[i].t=(char)i; }
  long acc=0;
  for (long p=0;p<64;++p) for (long i=0;i<8192;++i) acc += arr[i].v;
  unsigned char o[1]={(unsigned char)('0'+(acc&7))}; sys3(1,1,(long)o,1); ex(0);
}
