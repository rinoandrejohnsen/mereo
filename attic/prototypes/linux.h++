// linux.h++ : freestanding RAII wrappers over the Linux x86-64 syscall ABI.
//
// Built for: -static -ffreestanding -nostartfiles -nodefaultlibs -fwhole-program
//            -fno-rtti -fno-exceptions  (and -std=c++23, required for `namespace
//            linux` -- the GNU `linux`/`unix` macros only vanish in strict mode).
//
// Design (the conclusion of "everything is a file" -> "everything is a file
// DESCRIPTOR"): the foundational type is `file_descriptor`, a move-only RAII
// handle that owns one fd and closes it exactly once. `file` and `socket`
// *compose* a file_descriptor (they are not a class hierarchy); `process` -- the
// odd one out, identified by a pid -- can be pulled into the same fd world via
// pidfd_open(). So the uniform read/write/close interface lives in ONE place and
// everything else delegates to it; no virtuals, no vtable cost.
//
// `mapping` is the one resource that owns memory rather than an fd: an (address,
// length) pair claimed with mmap and released with munmap. It must remember its
// length -- unlike close(fd), munmap needs the size -- but the RAII shape is the
// same as the rest: move-only, freed exactly once on scope exit.
//
// Processes do form a small class hierarchy, because a program IS a process:
// `process` is the non-owning base (a pid you can signal / probe / open a pidfd
// to); `subprocess : process` is one we spawned and own (move-only, SIGKILL +
// reap on drop); and `app : process` is us, the current process (argv, env,
// spawn-children, exit). `app` is deliberately NOT a `subprocess` -- we do not
// own ourselves, so destroying an app must never reap our own pid.
//
// Error handling is exception-free, like the rest of the linux/ subsystem: every
// operation returns the raw kernel result (via linux::call). Values in
// -4095..-1 are -errno -- check is_ok(), or linux::failed()/linux::errno_of(). A
// failed "constructor" just yields a handle with is_ok() == false.
# pragma once

# include "linux/call.h++"   // linux::call (exception-free), exit, failed, errno_of

namespace linux {

  // -- file_descriptor : the foundational handle ------------------------------
  //
  // Owns exactly one fd; closes it once, on scope exit. Move-only: copying an fd
  // means dup(2), which must be explicit (see duplicate()), never implicit. A
  // moved-from handle is inert (fd == -1) so it cannot double-close. A handle
  // holding a negative value (e.g. an open that failed) is simply !is_ok() and is
  // never closed.
  class [[nodiscard]] file_descriptor {
    public:
      file_descriptor () = default;                    // empty: is_ok() == false
      // Adopt ownership of an already-open fd: the destructor WILL close it. Do
      // not wrap a borrowed fd you do not own (e.g. 0/1/2) -- that would close
      // stdin/out/err. Write to those raw, or release() before scope end.
      explicit file_descriptor (long fd) : fd_ (fd) {}

      file_descriptor (file_descriptor&& o) noexcept : fd_ (o.fd_) { o.fd_ = -1; }
      file_descriptor& operator= (file_descriptor&& o) noexcept {
        if (this == &o) return *this;
        close (); fd_ = o.fd_; o.fd_ = -1;
        return *this;
      }
      file_descriptor (const file_descriptor&) = delete;            // no double-close
      file_descriptor& operator= (const file_descriptor&) = delete;

      ~file_descriptor () { close (); }

      [[nodiscard]] bool is_ok () const { return fd_ >= 0; }
      [[nodiscard]] long get () const { return fd_; }

      [[nodiscard]] long read (void* buffer, unsigned long size) {
        return call (calls::read, fd_, buffer, size);
      }
      [[nodiscard]] long write (const void* buffer, unsigned long size) {
        return call (calls::write, fd_, buffer, size);
      }
      [[nodiscard]] long seek (long offset, int whence) {
        return call (calls::lseek, fd_, offset, (long) whence);
      }

      // The only way to copy an fd: a conscious dup(2).
      [[nodiscard]] file_descriptor duplicate () const {
        return file_descriptor (call (calls::dup, fd_));
      }
      // Give up ownership; the caller must now close the returned fd.
      [[nodiscard]] long release () { long f = fd_; fd_ = -1; return f; }

      void close () {
        if (fd_ >= 0) { call (calls::close, fd_); fd_ = -1; }
      }

    private:
      long fd_ = -1;
  };

  // -- file : open(2) + the fd's I/O ------------------------------------------
  class [[nodiscard]] file {
    public:
      // Named flags/modes so call sites avoid magic numbers (octal O_* values).
      enum flag : long {
        read_only  = 0,        // O_RDONLY
        write_only = 1,        // O_WRONLY
        read_write = 2,        // O_RDWR
        create     = 0x40,     // O_CREAT
        truncate   = 0x200,    // O_TRUNC
        append     = 0x400,    // O_APPEND
      };
      enum whence : int { set = 0, current = 1, end = 2 }; // SEEK_*

      // Two forms so the common case is a bare 2-argument open(2) -- no mode
      // register is set up, matching a hand-written open. The 3-arg form is for
      // when you create a file (O_CREAT) and must supply a permission mode.
      file (const char* path, long flags)
        : fd_ (call (calls::open, path, flags)) {}
      file (const char* path, long flags, long mode)
        : fd_ (call (calls::open, path, flags, mode)) {}

      [[nodiscard]] bool is_ok () const { return fd_.is_ok (); }
      [[nodiscard]] long fd () const { return fd_.get (); }
      [[nodiscard]] file_descriptor&       descriptor ()       { return fd_; }
      [[nodiscard]] const file_descriptor& descriptor () const { return fd_; }

      [[nodiscard]] long read  (void* b, unsigned long n)       { return fd_.read (b, n); }
      [[nodiscard]] long write (const void* b, unsigned long n) { return fd_.write (b, n); }
      [[nodiscard]] long seek  (long off, int w)                { return fd_.seek (off, w); }
      [[nodiscard]] long sync  ()  { return call (calls::fsync, fd_.get ()); }

    private:
      file_descriptor fd_;
  };

  // -- mapping : mmap(2) memory, RAII-unmapped --------------------------------
  //
  // Claims memory from the kernel and munmaps it on scope exit. Because munmap
  // needs the length, the handle owns an (address, length) pair, not just a
  // pointer. mmap is effectively the only way to obtain memory in a freestanding
  // program -- brk/sbrk move one global break pointer and do not compose into
  // independent RAII allocations.
  class [[nodiscard]] mapping {
    public:
      enum prot : long { none = 0, read = 1, write = 2, exec = 4 };   // PROT_*
      enum flag : long { shared = 0x01, priv = 0x02,                  // MAP_*
                         fixed  = 0x10, anonymous = 0x20 };

      // Claim `size` bytes of fresh, zeroed, private anonymous memory -- the
      // common "just give me memory" case. !is_ok() on failure (nothing to free).
      explicit mapping (unsigned long size, long protection = read | write)
        : mapping ((void*) nullptr, size, protection, priv | anonymous, -1L, 0L) {}

      // General mmap(2): map `fd` at `offset` (or anonymous when fd == -1). Pass
      // a file's descriptor here (f.fd()) to memory-map a file.
      mapping (void* addr, unsigned long size, long protection,
               long flags, long fd, long offset) : size_ (size) {
        long r = call (calls::mmap, addr, size, protection, flags, fd, offset);
        if (failed (r)) { ptr_ = nullptr; size_ = 0; return; }   // failed: nothing to unmap
        ptr_ = (void*) r;
      }

      // Move-only: two handles unmapping one region would double-free. A
      // moved-from mapping is inert (null/0) so its destructor does nothing.
      mapping (mapping&& o) noexcept : ptr_ (o.ptr_), size_ (o.size_) {
        o.ptr_ = nullptr; o.size_ = 0;
      }
      mapping& operator= (mapping&& o) noexcept {
        if (this == &o) return *this;            // guard self-assignment
        unmap ();
        ptr_ = o.ptr_; size_ = o.size_;
        o.ptr_ = nullptr; o.size_ = 0;
        return *this;
      }
      mapping (const mapping&) = delete;
      mapping& operator= (const mapping&) = delete;

      ~mapping () { unmap (); }

      [[nodiscard]] bool is_ok () const { return ptr_ != nullptr; }
      [[nodiscard]] void* data () const { return ptr_; }
      [[nodiscard]] unsigned long size () const { return size_; }
      template <class type> [[nodiscard]] type* as () const { return (type*) ptr_; }

      void unmap () {
        if (ptr_) { call (calls::munmap, ptr_, size_); ptr_ = nullptr; size_ = 0; }
      }
      // Relinquish ownership; the caller must munmap it (grab size() first).
      [[nodiscard]] void* release () { void* p = ptr_; ptr_ = nullptr; size_ = 0; return p; }

    private:
      void* ptr_ = nullptr;
      unsigned long size_ = 0;
  };

  // -- socket : socket(2) family ---------------------------------------------
  //
  // Addresses are passed as an opaque (void*, len) pair so this header drags in
  // no networking structs; the caller supplies its own sockaddr_in / sockaddr_un.
  class [[nodiscard]] socket {
    public:
      enum class domain : long { local = 1, inet = 2, inet6 = 10 };   // AF_*
      enum class kind   : long { stream = 1, datagram = 2, raw = 3 }; // SOCK_*

      socket (domain d, kind k, long protocol = 0)
        : fd_ (call (calls::socket, (long) d, (long) k, protocol)) {}

      // Adopt an existing fd (e.g. one half of a socketpair, or an accepted fd).
      explicit socket (file_descriptor&& fd) : fd_ (static_cast<file_descriptor&&> (fd)) {}

      [[nodiscard]] bool is_ok () const { return fd_.is_ok (); }
      [[nodiscard]] long fd () const { return fd_.get (); }
      [[nodiscard]] file_descriptor& descriptor () { return fd_; }

      [[nodiscard]] long bind (const void* addr, unsigned long len) {
        return call (calls::bind, fd_.get (), addr, len);
      }
      [[nodiscard]] long connect (const void* addr, unsigned long len) {
        return call (calls::connect, fd_.get (), addr, len);
      }
      [[nodiscard]] long listen (long backlog) {
        return call (calls::listen, fd_.get (), backlog);
      }
      // Returns a NEW socket for the accepted connection (!is_ok() on error).
      [[nodiscard]] socket accept (void* addr = nullptr, unsigned int* len = nullptr) {
        return socket (file_descriptor (call (calls::accept, fd_.get (), addr, len)));
      }

      [[nodiscard]] long send (const void* b, unsigned long n, long flags = 0) {
        return call (calls::sendto, fd_.get (), b, n, flags, (const void*) nullptr, 0L);
      }
      [[nodiscard]] long recv (void* b, unsigned long n, long flags = 0) {
        return call (calls::recvfrom, fd_.get (), b, n, flags,
                     (void*) nullptr, (unsigned int*) nullptr);
      }

    private:
      file_descriptor fd_;
  };

  // -- process : a process, referred to by pid --------------------------------
  //
  // The base notion shared by everything that *is* a process. You can ask its
  // pid, send it a signal, probe whether it is alive, or open a pidfd to it --
  // which pulls even a process into the uniform fd interface ("everything is a
  // file descriptor", Linux 5.3+). This base is a non-owning reference: copying
  // it is fine and its destructor does nothing. Ownership and cleanup of a
  // *spawned* process live in the derived `subprocess`; *we ourselves* are the derived
  // `app`. Both inherit these operations because both genuinely are processes.
  class process {
    public:
      process () = default;
      explicit process (long pid) : pid_ (pid) {}

      [[nodiscard]] bool is_ok () const { return pid_ > 0 || pid_ == self_; }
      [[nodiscard]] long pid () const { return resolve (); }

      // Send a signal (kill(2)). Signal 0 delivers nothing and merely probes for
      // existence + permission, which is what running() uses.
      long kill (int signal) const {
        long p = resolve ();
        return p > 0 ? call (calls::kill, p, (long) signal) : -1;
      }
      [[nodiscard]] bool running () const {
        long p = resolve ();
        return p > 0 && call (calls::kill, p, 0L) == 0;
      }

      // A pidfd: readable / pollable / closable like any fd, and immune to pid
      // reuse. !is_ok() descriptor on failure.
      [[nodiscard]] file_descriptor pidfd (long flags = 0) const {
        return file_descriptor (call (calls::pidfd_open, resolve (), flags));
      }

    protected:
      // pid_ is a real pid (> 0), or -1 (empty), or self_ -- the marker for "the
      // current process", which resolve() turns into getpid() lazily on first
      // identity use and caches. So an `app` that never asks its pid never pays
      // the syscall. Every public method goes through resolve(), so the marker
      // never reaches a syscall; 0 is never a real userspace pid, so it is safe.
      static constexpr long self_ = 0;
      struct self_marker {};
      explicit process (self_marker) : pid_ (self_) {}
      long resolve () const {
        if (pid_ == self_) pid_ = call (calls::getpid);
        return pid_;
      }
      mutable long pid_ = -1;   // mutable: resolve() fills the self marker lazily
  };

  // -- subprocess : a process we spawned and own ------------------------------
  //
  // process + ownership. Move-only -- two owners of one pid would double-reap /
  // double-signal (and after pid reuse hit an unrelated process) -- and its
  // destructor guarantees cleanup: SIGKILL (uncatchable, so it never hangs) then
  // reap, leaving neither a runaway orphan nor a zombie. wait() to reap on your
  // own terms; detach() to let the subprocess outlive the handle. A moved-from
  // handle is inert (pid == -1).
  class [[nodiscard]] subprocess : public process {
    public:
      explicit subprocess (long pid) : process (pid) {}

      subprocess (subprocess&& o) noexcept : process (o.pid_) { o.pid_ = -1; }
      subprocess& operator= (subprocess&& o) noexcept {
        if (this == &o) return *this;
        cleanup (); pid_ = o.pid_; o.pid_ = -1;
        return *this;
      }
      subprocess (const subprocess&) = delete;
      subprocess& operator= (const subprocess&) = delete;

      ~subprocess () { cleanup (); }

      // fork(2) + execve(2): the new process execs `path` (never returning here,
      // or exiting 127 if exec fails); the parent gets the owning handle. !is_ok()
      // if fork itself failed.
      [[nodiscard]] static subprocess spawn (const char* path,
                                             char* const argv[],
                                             char* const envp[]) {
        long pid = call (calls::fork);
        if (pid == 0) {                                 // in the child
          call (calls::execve, path, argv, envp);       // returns only on failure
          exit (127);
        }
        return subprocess (pid);                        // parent
      }

      // Block until it terminates and reap it. Afterwards the handle is spent
      // (pid invalidated) so the destructor will not signal a recycled pid.
      // `status` (optional) receives the raw wait status; returns the reaped pid
      // (or, under WNOHANG, 0 if still running; or -errno).
      long wait (int* status = nullptr, long options = 0) {
        if (pid_ <= 0) return -1;
        long r = call (calls::wait4, pid_, status, options, (void*) nullptr);
        if (r == pid_) pid_ = -1;        // actually reaped -> never touch pid again
        return r;
      }

      // Relinquish ownership: the subprocess will outlive this handle (no kill/reap).
      long detach () { long p = pid_; pid_ = -1; return p; }

    private:
      void cleanup () {
        if (pid_ <= 0) return;                                           // nothing to reap
        call (calls::kill, pid_, 9L);                                    // SIGKILL
        call (calls::wait4, pid_, (void*) nullptr, 0L, (void*) nullptr);
        pid_ = -1;
      }
  };

  // -- app : the current process (the one the kernel started us as) -----------
  //
  // Also a process -- so it inherits pid()/kill()/running()/pidfd(), now acting
  // on *us* (our pid is getpid(), resolved lazily). It is NOT a `subprocess`: we
  // do not own ourselves, so there is no kill+reap destructor. On top of the base
  // it adds our command line, environment, and spawn() (the app's access to the
  // process world, returning a `subprocess`).
  //
  // THE MAIN CLASS: your program derives from this, and the framework (run())
  // instantiates exactly one -- by reference only, never copied or moved. Because
  // there is exactly one and its lifetime IS the process's, its destructor is
  // where the process exits: once start() has returned and every member has been
  // cleaned up, ~app makes the exit syscall with the code start() produced.
  class app : public process {
      // run() is the sole creator; it records status_ before the one instance dies.
      template <class application> friend void run (long*);

    public:
      // We keep only the initial stack pointer ([argc][argv...][NULL][envp...]
      // [NULL]) and parse argc/argv/env from it ON DEMAND; our pid is likewise
      // resolved lazily by the base (process(self_marker)). So an app that never
      // asks for its command line, environment, or identity pays nothing -- no
      // eager getpid, no parsing, nothing stored or passed but one pointer (which
      // itself drops out if the entry ignores it).
      explicit app (long* stack) : process (process::self_marker {}), stack_ (stack) {}

      // Framework-only, single instance: never copied or moved, only referenced.
      // (Copying "the current process" is meaningless, and would make ~app -- which
      // exits -- fire more than once.)
      app (const app&)            = delete;
      app& operator= (const app&) = delete;
      app (app&&)                 = delete;
      app& operator= (app&&)      = delete;

      // The process exits HERE. ~app is the last base destroyed, so it runs after
      // start() returned and after every member of the program was cleaned up.
      ~app () { linux::exit (status_); }

      // Identity beyond the base (pid()/kill()/running()/pidfd() come from it).
      [[nodiscard]] long parent_pid () const { return call (calls::getppid); }
      [[nodiscard]] long uid        () const { return call (calls::getuid); }
      [[nodiscard]] long gid        () const { return call (calls::getgid); }

      // Command line -- parsed from the stack only when asked.
      [[nodiscard]] long        argc ()       const { return stack_[0]; }
      [[nodiscard]] char**      argv ()       const { return (char**) (stack_ + 1); }
      [[nodiscard]] const char* arg  (long i) const {
        return (i >= 0 && i < argc ()) ? argv ()[i] : nullptr;
      }

      // Environment: the raw NULL-terminated block (just past argv[] and its
      // NULL), or a lookup by name returning the value after '=' (or nullptr).
      [[nodiscard]] char** environment () const { return (char**) (stack_ + stack_[0] + 2); }
      [[nodiscard]] const char* env (const char* name) const {
        for (char** e = environment (); *e; ++e) {
          const char* s = *e; const char* n = name;
          while (*n && *s == *n) { ++s; ++n; }
          if (*n == '\0' && *s == '=') return s + 1;
        }
        return nullptr;
      }

      // Launch a subprocess (app -> subprocess), inheriting our environment
      // unless one is given.
      [[nodiscard]] subprocess spawn (const char* path, char* const argv[],
                                      char* const envp[] = nullptr) const {
        return subprocess::spawn (path, argv, envp ? envp : environment ());
      }

      // Terminate the whole process now. Prefer returning from your entry so
      // destructors run (exit() skips them) -- see run() / LINUX_START.
      [[noreturn]] void exit (int code) const { linux::exit (code); }

    protected:
      int status_ = 0;          // exit code: set it directly in a void start(), or
                                // return it from an int start(); ~app exits with it.
    private:
      long* stack_ = nullptr;   // the initial stack; argv/env parsed lazily from it
  };

  // -- entry-point safety -----------------------------------------------------
  //
  // Your program is a CLASS that derives from `app`: it *is* the current process,
  // so arg(), env(), pid(), spawn(), ... are its own inherited members. run()
  // constructs it from the initial stack, calls its start(), and -- only after it
  // and all its members have been destroyed -- exits with the returned code.
  //
  // exit() is a raw syscall that runs NO destructors, so the destroy-before-exit
  // ordering here is what makes RAII cleanup actually happen. `application` is a
  // template parameter, so start() is a direct, inlinable call; anything the
  // program never touches (argv, env, identity) still costs nothing (all lazy).
  // always_inline + flatten fold the whole program -- the app construction,
  // start(), and exit() -- into the entry trampoline, so there is no call into a
  // separate start(), no `app` object materialized on the stack, and the body
  // lowers like a hand-written _start (matching crix.h++'s flattened entry).
  template <class application>
  [[gnu::always_inline, gnu::flatten, noreturn]] inline void run (long* initial_stack) {
    static_assert (__is_base_of (app, application),
                   "LINUX_START's argument must be a class deriving from linux::app");
    // Construct the one instance and run it; the closing brace destroys it --
    // members first, then ~app, which makes the exit syscall. So exit happens
    // after all cleanup, expressed as the program's own destruction. start() may
    // return its exit code (int) or set status_ itself and return void.
    { application self (initial_stack);
      if constexpr (requires { self.status_ = self.start (); })
        self.status_ = self.start ();   // int start(): record the returned code
      else
        self.start ();                  // void start(): the program set status_
    }
    __builtin_unreachable ();   // ~app above never returns
  }
}

// Emit a freestanding entry point for an application CLASS -- one that derives
// from linux::app and provides `int start()`. Expand ONCE, in a single TU (when
// you are not using crix.h++, which supplies its own _start):
//
//   class program : public linux::app {
//   public:
//     using linux::app::app;            // inherit the entry constructor
//     int start () { /* use arg(), env(), spawn(), ... directly */ return 0; }
//   };
//   LINUX_START(program)
//
// The asm captures the initial %rsp (argc/argv/envp) before any prologue runs,
// 16-byte-aligns the stack, and hands off to C++. Cleanup is guaranteed: the
// program's members are destroyed, then ~app makes the exit syscall.
#define LINUX_START(application)                                                \
  extern "C" [[gnu::used, gnu::externally_visible, noreturn]]                   \
  void linux_entry_trampoline (long* initial_stack) {                          \
    ::linux::run<application> (initial_stack);                                  \
  }                                                                            \
  asm (".globl _start\n"                                                       \
       "_start:\n"                                                             \
       /* No `xor %ebp,%ebp`: the outermost-frame marker is dead in a no-unwind, \
          -fomit-frame-pointer program (Linux already zeroes registers at exec). */ \
       "  movq %rsp, %rdi\n"          /* initial stack (argc/argv/env) -> arg0 */ \
       "  andq $-16, %rsp\n"          /* 16-byte align before calling C++ */   \
       "  call linux_entry_trampoline\n");
