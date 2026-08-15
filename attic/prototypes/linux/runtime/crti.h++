# pragma once

# include "../call.h++"

namespace giron::linux::runtime {
  static ThreadAttributes main_thread_attrib;

  // Data structure to capture properties of the linux/ELF TLS image.
  struct TLSImage {
    // The load address of the TLS.
    uintptr_t address;

    // The byte size of the TLS image consisting of both initialized and
    // uninitialized memory. In ELF executables, it is size of .tdata + size of
    // .tbss. Put in another way, it is the memsz field of the PT_TLS header.
    uintptr_t size;

    // The byte size of initialized memory in the TLS image. In ELF exectubles,
    // this is the size of .tdata. Put in another way, it is the filesz of the
    // PT_TLS header.
    uintptr_t init_size;

    // The alignment of the TLS layout. It assumed that the alignment
    // value is a power of 2.
    uintptr_t align;
  };

  // Linux manpage on `proc(5)` says that the aux vector is an array of
  // unsigned long pairs.
  // (see: https://man7.org/linux/man-pages/man5/proc.5.html)
  using AuxEntryType = unsigned long;
  // Using the naming convention from `proc(5)`.
  // TODO: Would be nice to use the aux entry structure from elf.h when available.
  struct AuxEntry {
    AuxEntryType id;
    AuxEntryType value;
  };

  struct AppProperties {
    // Page size used for the application.
    uintptr_t page_size;

    Args *args;

    // The properties of an application's TLS image.
    TLSImage tls;

    // Environment data.
    uintptr_t *env_ptr;

    // Auxiliary vector data.
    AuxEntry *auxv_ptr;
  };

  [[gnu::weak]] extern AppProperties app;

  // The descriptor of a thread's TLS area.
  struct TLSDescriptor {
    // The size of the TLS area.
    uintptr_t size = 0;

    // The address of the TLS area. This address can be passed to cleanup
    // functions like munmap.
    uintptr_t addr = 0;

    // The value the thread pointer register should be initialized to.
    // Note that, dependending the target architecture ABI, it can be the
    // same as |addr| or something else.
    uintptr_t tp = 0;

    constexpr TLSDescriptor() = default;
  };

  // Create and initialize the TLS area for the current thread. Should not
  // be called before app.tls has been initialized.
  void init_tls(TLSDescriptor &tls);

  // Cleanup the TLS area as described in |tls_descriptor|.
  void cleanup_tls(uintptr_t tls_addr, uintptr_t tls_size);

  // Set the thread pointer for the current thread.
  bool set_thread_ptr(uintptr_t val);


  [[noreturn]]
  void start () {
    auto tid = linux::call (
      linux::calls::getpid
    );

    main_thread_attrib.tid = static_cast<int>(tid);

    int retval = main (
      static_cast <int> (app.args->argc),
      reinterpret_cast <char **> (app.args->argv),
      reinterpret_cast <char **> (env_ptr)
    );

    exit (retval);
  }
}

[[noreturn]]
void _start () {
  // This TU is compiled with -fno-omit-frame-pointer. Hence, the previous
  // value of the base pointer is pushed on to the stack. So, we step over
  // it (the "+ 1" below) to get to the args.
  LIBC_NAMESPACE::app.args = reinterpret_cast<LIBC_NAMESPACE::Args *>(
    reinterpret_cast<uintptr_t *>(__builtin_frame_address(0)) + 1);

  // The x86_64 ABI requires that the stack pointer is aligned to a 16-byte
  // boundary. We align it here but we cannot use any local variables created
  // before the following alignment. Best would be to not create any local
  // variables before the alignment. Also, note that we are aligning the stack
  // downwards as the x86_64 stack grows downwards. This ensures that we don't
  // tread on argc, argv etc.
  // NOTE: Compiler attributes for alignment do not help here as the stack
  // pointer on entry to this _start function is controlled by the OS. In fact,
  // compilers can generate code assuming the alignment as required by the ABI.
  // If the stack pointers as setup by the OS are already aligned, then the
  // following code is a NOP.
  asm volatile ("andq $0xfffffffffffffff0, %rsp\n\t");
  asm volatile ("andq $0xfffffffffffffff0, %rbp\n\t");

  raw::linux::runtime::start ();
