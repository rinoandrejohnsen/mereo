// Freestanding C++ side of the RAII parity suite. A `Mark` closes a sentinel
// fd in its destructor, so `strace -e close` on the run yields the exact C++
// destruction order -- the ground truth mereo's scope RAII must reproduce.
//   Mark{101} <-> mereo mark_a, 102<->b, 103<->c, 104<->d
#pragma once

static inline long sysclose(long fd) {
    long r;
    __asm__ volatile ("syscall" : "=a"(r) : "a"(3L), "D"(fd) : "rcx", "r11", "memory");
    return r;
}
[[noreturn]] static inline void sysexit(long c) {
    __asm__ volatile ("syscall" : : "a"(231L), "D"(c) : "memory");
    __builtin_unreachable();
}

struct Mark {
    long fd;
    ~Mark() { sysclose(fd); }
};
