// io.h++ : canonical freestanding RAII file handle (no libc, no exceptions).
//
// Design goals (so cleanup is "always correct" by construction):
//   * owns exactly one fd; closes it exactly once, on scope exit;
//   * move-only -- copying an fd would double-close, so copy is deleted;
//   * moved-from handle is inert (fd_ = -1) so it can't close twice;
//   * [[nodiscard]] guards: a stray temporary `file(...)` and ignored
//     read()/write() results both warn (an ignored result is an unhandled error).
//
// No exceptions: a failed open just yields a handle with ok() == false; check it.
#pragma once

static inline long syscall1(long n, long a1) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1) : "rcx", "r11", "memory");
    return ret;
}
static inline long syscall3(long n, long a1, long a2, long a3) {
    long ret;
    __asm__ volatile ("syscall" : "=a"(ret) : "a"(n), "D"(a1), "S"(a2), "d"(a3) : "rcx", "r11", "memory");
    return ret;
}

class [[nodiscard]] file {
  public:
    // Fallible "construction" without exceptions: open and store the result.
    file(const char* path, long flags, long mode = 0)
        : fd_(syscall3(2, (long)path, flags, mode)) {}

    // Adopt an already-open descriptor. NOTE: this takes ownership and WILL close
    // it -- do not wrap a borrowed fd like stdout (write to it raw, or release()).
    explicit file(long fd) : fd_(fd) {}

    // Move-only: transfer ownership, leave the source inert.
    file(file&& other) noexcept : fd_(other.fd_) { other.fd_ = -1; }
    file& operator=(file&& other) noexcept {
        if (this != &other) { reset(); fd_ = other.fd_; other.fd_ = -1; }
        return *this;
    }
    file(const file&) = delete;            // copying would double-close
    file& operator=(const file&) = delete;

    ~file() { reset(); }

    [[nodiscard]] bool ok() const { return fd_ >= 0; }
    [[nodiscard]] long fd() const { return fd_; }

    [[nodiscard]] long read(void* buf, unsigned long n) {
        return syscall3(0, fd_, (long)buf, n);
    }
    [[nodiscard]] long write(const void* buf, unsigned long n) {
        return syscall3(1, fd_, (long)buf, n);
    }

    // Relinquish ownership; caller becomes responsible for closing.
    [[nodiscard]] long release() {
        long f = fd_;
        fd_ = -1;
        return f;
    }

  private:
    long fd_ = -1;
    void reset() { if (fd_ >= 0) syscall1(3, fd_); }
};
