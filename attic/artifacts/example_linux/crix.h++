#pragma once

#include <stdint.h>
#include <stddef.h>
#include "linux/call.h++"

namespace arc::exception {
  constexpr size_t MAX_EXCEPTION_ACTIONS = 4096;

  // Structure-of-arrays landing-pad table.
  //
  // The binary search probes only pc_end, so it lives in its own dense uint32
  // array: 16 keys per cache line, and the whole key array for the 4096-entry
  // cap fits in 16 KiB (L1). pc_start and landing_pad are read once, after the
  // search, so they sit in parallel arrays out of the hot path.
  //
  // Addresses are 32-bit. That is sound only because this unwinder targets
  // non-PIE, statically linked executables whose code and landing pads load
  // below 4 GiB (see the `ld -no-pie` step in builder.c++). Widen to 64-bit if
  // that assumption is ever broken.
  struct FastLookupData {
      size_t   count;
      uint32_t pc_end     [MAX_EXCEPTION_ACTIONS];
      uint32_t pc_start   [MAX_EXCEPTION_ACTIONS];
      uint32_t landing_pad[MAX_EXCEPTION_ACTIONS];
      // Per-function callee-saved save-map (see builder.c++): rbp-relative slot
      // (8-byte units below rbp; 0 = not saved) for {rbx,r12,r13,r14,r15}.
      size_t   fn_count;
      uint32_t fn_end  [MAX_EXCEPTION_ACTIONS];
      uint32_t fn_start[MAX_EXCEPTION_ACTIONS];
      int8_t   save_slot[MAX_EXCEPTION_ACTIONS][6];   // {rbx,rbp,r12,r13,r14,r15}, CFA-relative
      uint32_t fn_cfa_offset[MAX_EXCEPTION_ACTIONS];  // CFA = rsp + cfa_offset (no frame pointer)
      // This function's landing-pad call-sites: [fn_cs_first, +fn_cs_count) of
      // the pc_start/pc_end/landing_pad arrays. Lets one function lookup yield
      // the save-map and the slice to scan for the landing pad (see find_unwind).
      uint32_t fn_cs_first[MAX_EXCEPTION_ACTIONS];
      uint32_t fn_cs_count[MAX_EXCEPTION_ACTIONS];
      // Monomorphic throw sites: jump straight to the catch, no walk (option 1).
      size_t   spec_count;
      uint32_t spec_throw_pc [MAX_EXCEPTION_ACTIONS];
      uint32_t spec_catch_lp [MAX_EXCEPTION_ACTIONS];
      uint32_t spec_cfa_delta[MAX_EXCEPTION_ACTIONS];
  };

  extern FastLookupData fast_lookup_data;

  // cfa_offset == 0 means "pc is in no known function" (top of stack / stop).
  struct UnwindInfo { void* landing_pad; const int8_t* save_map; uint32_t cfa_offset; };

  // One lookup per frame. A single branchless search over the per-function table
  // locates the frame's function; its save-map and CFA offset are then immediate,
  // and its landing pad (if any) is found by scanning only that function's own
  // call-site slice -- a few entries -- instead of a second whole-table search.
  inline UnwindInfo find_unwind(uintptr_t pc) {
    const FastLookupData& d = fast_lookup_data;
    const uint32_t key = static_cast<uint32_t>(pc);
    if (d.fn_count == 0) return { nullptr, nullptr, 0 };

    const uint32_t* base = d.fn_end;
    size_t len = d.fn_count;
    while (len > 1) {
      size_t half = len / 2;
      base += half & -static_cast<size_t>(base[half - 1] <= key);
      len -= half;
    }
    size_t fi = static_cast<size_t>(base - d.fn_end) + static_cast<size_t>(*base <= key);
    if (fi >= d.fn_count || key < d.fn_start[fi]) return { nullptr, nullptr, 0 };

    void* lp = nullptr;
    const uint32_t end = d.fn_cs_first[fi] + d.fn_cs_count[fi];
    for (uint32_t j = d.fn_cs_first[fi]; j < end; j++)
      if (key >= d.pc_start[j] && key < d.pc_end[j]) {
        lp = reinterpret_cast<void*>(static_cast<uintptr_t>(d.landing_pad[j]));
        break;
      }
    return { lp, d.save_slot[fi], d.fn_cfa_offset[fi] };
  }

  template <typename T> struct ClassFromMethod;
  template <typename C, typename R, typename... Args>
  struct ClassFromMethod<R (C::*)(Args...)> { using Type = C; };
  template <typename C, typename R, typename... Args>
  struct ClassFromMethod<R (C::*)(Args...) noexcept> { using Type = C; };
}

namespace linux {
  class application {
    public:
      class arguments {
        public:
          unsigned long count;
          unsigned long vector;
      };
  };
}

template <auto StartMethod> [[gnu::always_inline, gnu::flatten, noreturn]] inline void start (linux::application::arguments* args) {
  using linux_application = typename arc::exception::ClassFromMethod<decltype(StartMethod)>::Type;

  try {
      if constexpr (requires { linux_application(args); }) {
          linux_application app(args);
          (app.*StartMethod)();
      } else {
          linux_application app;
          (app.*StartMethod)();
      }
  } catch (...) {
      linux::exit(1);
  }

  linux::exit(0);
};

#define START_APPLICATION(METHOD) \
  namespace arc::exception { \
      [[gnu::section(".fast_lookup_data")]] \
      FastLookupData fast_lookup_data = {}; \
  } \
  extern "C" { \
      char exception_buffer[256]; \
      void* __cxa_allocate_exception(size_t) throw() { return exception_buffer; } \
      /* Shadow copy of {rbx,rbp,r12,r13,r14,r15}. With no frame pointer, rbp is */ \
      /* an ordinary callee-saved register, so the unwinder restores all six as it */ \
      /* walks. The happy path keeps every register; the cost is on the throw. */ \
      static unsigned long __csr[6]; \
      [[gnu::always_inline]] inline void capture_csr() { \
          /* rbx,r12-r15 are still the throwing frame's values here (the prologue */ \
          /* saved but did not overwrite them); rbp is captured by the caller below */ \
          /* from its saved slot, since these entry points force a frame pointer. */ \
          asm volatile ("movq %%rbx,%0\n\t movq %%r12,%1\n\t movq %%r13,%2\n\t movq %%r14,%3\n\t movq %%r15,%4" \
              : "=m"(__csr[0]),"=m"(__csr[2]),"=m"(__csr[3]),"=m"(__csr[4]),"=m"(__csr[5])); \
      } \
      [[gnu::always_inline]] inline void unwind_loop(uintptr_t cfa, void* exc) { \
          for (;;) { \
              void* pc = *(void**)(cfa - 8); /* return address into the parent frame */ \
              arc::exception::UnwindInfo info = arc::exception::find_unwind((uintptr_t)pc - 1); \
              if (info.cfa_offset == 0) break; /* pc in no known function -> stop */ \
              void* landing_pad = info.landing_pad; \
              if (landing_pad != nullptr) { \
                  asm volatile ( \
                      "movq %1, %%rbx \n\t" "movq %2, %%rbp \n\t" "movq %3, %%r12 \n\t" \
                      "movq %4, %%r13 \n\t" "movq %5, %%r14 \n\t" "movq %6, %%r15 \n\t" \
                      "movq %8, %%rsp \n\t" "movq %7, %%rax \n\t" "movq $1, %%rdx \n\t" \
                      "jmp *%0 \n\t" \
                      : : "r" (landing_pad), \
                          "m"(__csr[0]),"m"(__csr[1]),"m"(__csr[2]),"m"(__csr[3]),"m"(__csr[4]),"m"(__csr[5]), \
                          "r" (exc), "r" (cfa) \
                      : "rbx","r12","r13","r14","r15","rax","rdx","memory" \
                  ); \
                  __builtin_unreachable(); \
              } \
              /* Unwind the parent frame: CFA_parent = cfa + cfa_offset; restore the */ \
              /* callee-saved regs it spilled (CFA-relative), advancing toward the handler. */ \
              uintptr_t parent_cfa = cfa + info.cfa_offset; \
              const int8_t* sm = info.save_map; \
              if (sm) for (int k = 0; k < 6; k++) \
                  if (sm[k]) __csr[k] = *(unsigned long*)(parent_cfa - sm[k]*8); \
              cfa = parent_cfa; \
          } \
          __builtin_trap(); \
      } \
      [[gnu::used, gnu::noipa, noreturn, gnu::optimize("no-omit-frame-pointer")]] void __cxa_throw(void* thrown_object, void*, void (*)(void*)) { \
          capture_csr(); \
          void** fp = (void**)__builtin_frame_address(0); \
          __csr[1] = (unsigned long)fp[0]; /* the throwing frame's saved rbp */ \
          uintptr_t cfa = (uintptr_t)fp + 16; /* CFA = rbp + 16 */ \
          /* Monomorphic fast path: if this throw site has a statically-unique catch, */ \
          /* jump straight there with no walk, no lookups, no _Unwind_Resume. */ \
          uint32_t site = (uint32_t)(uintptr_t)fp[1]; \
          const arc::exception::FastLookupData& d = arc::exception::fast_lookup_data; \
          for (size_t s = 0; s < d.spec_count; s++) \
              if (d.spec_throw_pc[s] == site) { \
                  uintptr_t lp = d.spec_catch_lp[s], rsp = cfa + d.spec_cfa_delta[s]; \
                  asm volatile ( \
                      "movq %1, %%rbx \n\t" "movq %2, %%rbp \n\t" "movq %3, %%r12 \n\t" \
                      "movq %4, %%r13 \n\t" "movq %5, %%r14 \n\t" "movq %6, %%r15 \n\t" \
                      "movq %8, %%rsp \n\t" "movq %7, %%rax \n\t" "movq $1, %%rdx \n\t" \
                      "jmp *%0 \n\t" \
                      : : "r" (lp), \
                          "m"(__csr[0]),"m"(__csr[1]),"m"(__csr[2]),"m"(__csr[3]),"m"(__csr[4]),"m"(__csr[5]), \
                          "r" (thrown_object), "r" (rsp) \
                      : "rbx","r12","r13","r14","r15","rax","rdx","memory" \
                  ); \
                  __builtin_unreachable(); \
              } \
          unwind_loop(cfa, thrown_object); \
          __builtin_unreachable(); \
      } \
      [[gnu::used, gnu::noipa, noreturn, gnu::optimize("no-omit-frame-pointer")]] void _Unwind_Resume(void* exc) { \
          capture_csr(); \
          void** fp = (void**)__builtin_frame_address(0); \
          __csr[1] = (unsigned long)fp[0]; \
          unwind_loop((uintptr_t)fp + 16, exc); \
          __builtin_unreachable(); \
      } \
      void* __cxa_begin_catch(void* exceptionObject) throw() { return exceptionObject; } \
      void __cxa_end_catch() { } \
      /* Referenced only from .eh_frame (DW.ref), so -fwhole-program would */ \
      /* dead-strip it without externally_visible. */ \
      [[gnu::externally_visible]] int __gxx_personality_v0() { return 0; } \
  } \
  /* The application ignores argc/argv, so _start never needs the entry %rsp -- */ \
  /* it can be an ordinary (non-naked) function with the whole app flattened in, */ \
  /* exactly like a C `void _start()`. (An app that needs argv would have to */ \
  /* restore the naked trampoline that captures %rsp before the prologue runs.) */ \
  extern "C" [[gnu::flatten, noreturn, gnu::externally_visible]] void _start() { \
    start<METHOD>(nullptr); \
  }
