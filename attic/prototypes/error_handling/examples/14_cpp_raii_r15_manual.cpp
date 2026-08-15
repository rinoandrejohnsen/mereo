#include <cstdio>

enum class error_code {
    decode_failed = 77,
};

struct error_info {
    error_code code;
    const char *message;
    const char *where;
};

static const error_info decode_error = {
    .code = error_code::decode_failed,
    .message = "decode failed",
    .where = "decode_payload",
};

static int work_units;

#define NOINLINE __attribute__((noinline))

#define EH_BEGIN() \
    __asm__ volatile("xor %%r15d, %%r15d" ::: "cc")

#define EH_RAISE(error_ptr)                                  \
    do {                                                     \
        const error_info *eh_error__ = (error_ptr);           \
        __asm__ volatile("mov %0, %%r15" :: "r"(eh_error__)); \
    } while (0)

#define EH_CHECK(cleanup_label)                              \
    __asm__ goto volatile(                                   \
        "test %%r15, %%r15\n\t"                              \
        "jnz %l0"                                            \
        :                                                    \
        :                                                    \
        : "cc"                                               \
        : cleanup_label)

#define EH_ERROR_PTR(out_ptr) \
    __asm__ volatile("mov %%r15, %0" : "=r"(out_ptr))

class tracked_resource {
public:
    explicit tracked_resource(const char *name)
        : name_(name)
    {
        std::printf("acquire %s\n", name_);
    }

    tracked_resource(const tracked_resource &) = delete;
    tracked_resource &operator=(const tracked_resource &) = delete;

    ~tracked_resource()
    {
        std::printf("release %s\n", name_);
    }

private:
    const char *name_;
};

static NOINLINE void decode_payload(int should_fail)
{
    ++work_units;

    if (should_fail) {
        EH_RAISE(&decode_error);
    }
}

static NOINLINE void parse_payload(int should_fail)
{
    ++work_units;
    decode_payload(should_fail);
}

static NOINLINE void run_operation(const char *name, int should_fail)
{
    std::printf("-- %s --\n", name);

    work_units = 0;
    EH_BEGIN();

    {
        tracked_resource file("file");
        tracked_resource buffer("buffer");

        parse_payload(should_fail);

        /*
         * This is the important C++ shape. The asm goto edge leaves the scope,
         * so the compiler emits destructors for file and buffer before the
         * eh_cleanup label is reached.
         */
        EH_CHECK(eh_cleanup);

        std::printf("operation: success, work_units=%d\n", work_units);
        return;
    }

eh_cleanup:
    const error_info *error = nullptr;
    EH_ERROR_PTR(error);

    std::printf("operation: cleanup after destructors, code=%d, where=%s, message=%s, work_units=%d\n",
                static_cast<int>(error->code),
                error->where,
                error->message,
                work_units);
}

int main()
{
    run_operation("c++ raii success case", 0);
    run_operation("c++ raii failure case", 1);
    return 0;
}
