# pragma once

# include "calls.h++"

// Exception-free syscall layer. The kernel's return value is passed straight
// back to the caller; a value in -4095..-1 is -errno (test it with failed() /
// errno_of()). Nothing here throws -- the whole linux/ subsystem handles errors
// by inspecting return values, so these headers compile under -fno-exceptions
// (and -fno-rtti). The higher-level RAII wrappers live in ../linux.h++.

register long volatile eh_error __asm__("r15");

namespace linux {
  // Index a forwarded parameter pack by position without pulling in <tuple>.
  // always_inline + `if constexpr` collapse this to "return the Nth argument",
  // so it compiles to nothing.
  template <int I>
  [[gnu::always_inline]] inline auto nth (auto first, auto... rest) {
    if constexpr (I == 0) return first;
    else return nth<I - 1> (rest...);
  }

  [[gnu::always_inline]]
  inline long call (calls call_id, auto... args) {
    long result;

    constexpr auto size = sizeof...(args);

    if constexpr (size == 0) {
      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id))
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 1) {
      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...))
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 2) {
      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...)),
          "S" (nth<1> (args...))
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 3) {
      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...)),
          "S" (nth<1> (args...)),
          "d" (nth<2> (args...))
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 4) {
      register __typeof__(nth<3> (args...)) __r10 __asm__("r10") = (nth<3> (args...));

      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...)),
          "S" (nth<1> (args...)),
          "d" (nth<2> (args...)),
          "r"(__r10)
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 5) {
      register __typeof__(nth<3> (args...)) __r10 __asm__("r10") = (nth<3> (args...));
      register __typeof__(nth<4> (args...)) __r8 __asm__("r8") = (nth<4> (args...));

      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...)),
          "S" (nth<1> (args...)),
          "d" (nth<2> (args...)),
          "r"(__r10), "r"(__r8)
        : "rcx", "r11", "memory"
      );
    } else if constexpr (size == 6) {
      register __typeof__(nth<3> (args...)) __r10 __asm__("r10") = (nth<3> (args...));
      register __typeof__(nth<4> (args...)) __r8 __asm__("r8") = (nth<4> (args...));
      register __typeof__(nth<5> (args...)) __r9 __asm__("r9") = (nth<5> (args...));

      asm volatile (
        "syscall"
        : "=a" (result)
        : "a" (static_cast<long> (call_id)),
          "D" (nth<0> (args...)),
          "S" (nth<1> (args...)),
          "d" (nth<2> (args...)),
          "r"(__r10), "r"(__r8), "r"(__r9)
        : "rcx", "r11", "memory"
      );
    }

    if (__builtin_expect(result < 0, 0)) {
      asm volatile ("" ::: "memory");
      eh_error = result;
    }
    return result;
  }

  // -- reading a syscall result ----------------------------------------------
  // The kernel signals failure by returning -errno in the -4095..-1 range.
  [[gnu::always_inline]] inline bool failed (long result) {
    return (unsigned long) result >= (unsigned long) -4095L;
  }
  [[gnu::always_inline]] inline int errno_of (long result) {  // 0 if ok, else +errno
    return failed (result) ? (int) -result : 0;
  }

  // exit never returns and cannot fail, so it skips the return value entirely --
  // just the bare syscall.
  [[gnu::always_inline, noreturn]] inline void exit (int code) {
    asm volatile (
      "syscall"
      : : "a" (static_cast<long> (calls::exit)), "D" ((long)code)
      : "rcx", "r11", "memory"
    );
    __builtin_unreachable ();
  }
}
