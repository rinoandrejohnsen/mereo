// RAII port of fast.c: the open/close resource cascade becomes a File object.
// The constructor performs open(2); the destructor performs close(2) -- so the
// "unwind_open" goto from fast.c is now just the object leaving scope. read() is
// a member. Still freestanding: raw syscalls, _start entry, no libc, no stack.

static inline void raw1(long n,long a){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a):"rcx","r11","memory");(void)r;}
static inline long raw2(long n,long a,long b){long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b):"rcx","r11","memory");return r;}
static inline long raw3(long n,long a,long b,long c) {long r;__asm__ volatile("syscall":"=a"(r):"a"(n),"D"(a),"S"(b),"d"(c):"rcx","r11","memory");return r;}

char  buffer[4096];

struct File {
  long fd;
  explicit File(const char *path) : fd(raw2(2, (long)path, 0)) {}   // open(path, O_RDONLY)
  ~File() { if (fd >= 0) raw1(3, fd); }                             // close(fd) on scope exit
  long read(void *buf, long n) { return raw3(0, fd, (long)buf, n); }
  bool ok() const { return fd >= 0; }
};

// All resource lifetime lives here; every return path runs ~File() (close).
static long run(void) {
  File f("lorem_ipsum.txt");
  if (!f.ok())   return 1;                                  // open failed: nothing to close

  long count = f.read(buffer, sizeof buffer);
  if (count < 0) return 2;                                  // ~File closes on the way out

  if (raw3(1, 1, (long)buffer, count) < 0) return 3;        // write(1, buffer, count)
  return 0;
}

extern "C" void _start(void){
  raw1(60, -run());                                         // exit(-code)
  __builtin_unreachable();
}
