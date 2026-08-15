register long volatile eh_error __asm__("r15");

using usize = __SIZE_TYPE__;
using uptr = __UINTPTR_TYPE__;

#define ALWAYS_INLINE inline __attribute__((always_inline))
#define EH_AUTORETURN __attribute__((eh_autoreturn, noinline))
#define SYSCALL_SET_R15_ON_ERROR                                           \
    "testq %%rax, %%rax\n\t"                                               \
    "cmovsq %%rax, %%r15\n\t"

constexpr long k_sys_read = 0;
constexpr long k_sys_write = 1;
constexpr long k_sys_close = 3;
constexpr long k_sys_exit = 60;
constexpr long k_sys_openat = 257;

constexpr long k_at_fdcwd = -100;
constexpr long k_o_rdonly = 0;

static ALWAYS_INLINE long ptr_arg(const void *ptr)
{
    return static_cast<long>(reinterpret_cast<uptr>(ptr));
}

static ALWAYS_INLINE long linux_syscall1(long number,
                                         long arg0)
{
    register long rax __asm__("rax") = number;
    register long rdi __asm__("rdi") = arg0;

    __asm__ volatile(
        "syscall\n\t"
        SYSCALL_SET_R15_ON_ERROR
        : "+a"(rax)
        : "D"(rdi)
        : "rcx", "r11", "memory", "cc");

    return rax;
}

static ALWAYS_INLINE long linux_syscall3(long number,
                                         long arg0,
                                         long arg1,
                                         long arg2)
{
    register long rax __asm__("rax") = number;
    register long rdi __asm__("rdi") = arg0;
    register long rsi __asm__("rsi") = arg1;
    register long rdx __asm__("rdx") = arg2;

    __asm__ volatile(
        "syscall\n\t"
        SYSCALL_SET_R15_ON_ERROR
        : "+a"(rax)
        : "D"(rdi),
          "S"(rsi),
          "d"(rdx)
        : "rcx", "r11", "memory", "cc");

    return rax;
}

static ALWAYS_INLINE long linux_syscall4(long number,
                                         long arg0,
                                         long arg1,
                                         long arg2,
                                         long arg3)
{
    register long rax __asm__("rax") = number;
    register long rdi __asm__("rdi") = arg0;
    register long rsi __asm__("rsi") = arg1;
    register long rdx __asm__("rdx") = arg2;
    register long r10 __asm__("r10") = arg3;

    __asm__ volatile(
        "syscall\n\t"
        SYSCALL_SET_R15_ON_ERROR
        : "+a"(rax)
        : "D"(rdi),
          "S"(rsi),
          "d"(rdx),
          "r"(r10)
        : "rcx", "r11", "memory", "cc");

    return rax;
}

static ALWAYS_INLINE int eh_open_readonly(const char *path)
{
    long result = linux_syscall4(k_sys_openat,
                                 k_at_fdcwd,
                                 ptr_arg(path),
                                 k_o_rdonly,
                                 0);
    return static_cast<int>(result);
}

static ALWAYS_INLINE long eh_read(int fd, void *buffer, usize length)
{
    long result = linux_syscall3(k_sys_read,
                                 fd,
                                 ptr_arg(buffer),
                                 static_cast<long>(length));
    return result;
}

static ALWAYS_INLINE void eh_write_once(int fd, const void *buffer, usize length)
{
    (void)linux_syscall3(k_sys_write,
                         fd,
                         ptr_arg(buffer),
                         static_cast<long>(length));
}

static ALWAYS_INLINE void eh_close(int fd)
{
    (void)linux_syscall1(k_sys_close, fd);
}

static __attribute__((noreturn)) ALWAYS_INLINE void eh_exit(int status)
{
    register long rax __asm__("rax") = k_sys_exit;
    register long rdi __asm__("rdi") = status;

    __asm__ volatile(
        "syscall\n\t"
        :
        : "a"(rax),
          "D"(rdi)
        : "rcx", "r11", "memory");

    __builtin_unreachable();
}

class file_descriptor {
public:
    ALWAYS_INLINE explicit file_descriptor(int fd)
        : fd_(fd)
    {
    }

    file_descriptor(const file_descriptor &) = delete;
    file_descriptor &operator=(const file_descriptor &) = delete;

    ALWAYS_INLINE ~file_descriptor()
    {
        if (fd_ >= 0) {
            eh_close(fd_);
        }
    }

    ALWAYS_INLINE int get() const
    {
        return fd_;
    }

private:
    int fd_;
};

static EH_AUTORETURN void copy_first_50_bytes(const char *path)
{
    int fd = -1;
    fd = eh_open_readonly(path);

    file_descriptor file(fd);

    char buffer[50];
    long bytes_read = 0;
    bytes_read = eh_read(file.get(), buffer, sizeof(buffer));

    eh_write_once(1, buffer, static_cast<usize>(bytes_read));
    eh_write_once(1, "\n", 1);
}

extern "C" __attribute__((noreturn)) void eh_start_body()
{
    eh_error = 0;

    copy_first_50_bytes("examples/dummy_input.txt");

    eh_exit(static_cast<int>(-eh_error));
}

extern "C" __attribute__((naked, used, noreturn)) void _start()
{
    __asm__ volatile(
        "xor %ebp, %ebp\n\t"
        "andq $-16, %rsp\n\t"
        "call eh_start_body\n\t"
        "ud2\n\t");
}
