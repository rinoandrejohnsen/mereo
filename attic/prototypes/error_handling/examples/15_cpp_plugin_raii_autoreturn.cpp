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

register const error_info * volatile eh_error __asm__("r15");

static int work_units;

#define NOINLINE __attribute__((noinline))
#define EH_AUTORETURN __attribute__((eh_autoreturn, noinline))

#define EH_BEGIN()           \
    do {                     \
        eh_error = nullptr;  \
    } while (0)

#define EH_RAISE(error_ptr)  \
    do {                     \
        eh_error = error_ptr; \
    } while (0)

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

static NOINLINE void read_header()
{
    ++work_units;
}

static NOINLINE void decode_payload(int should_fail)
{
    ++work_units;

    if (should_fail) {
        EH_RAISE(&decode_error);
    }
}

static NOINLINE void validate_payload()
{
    ++work_units;
}

static EH_AUTORETURN void parse_payload(int should_fail)
{
    ++work_units;

    read_header();
    decode_payload(should_fail);
    validate_payload();
}

static EH_AUTORETURN void run_inner(int should_fail)
{
    tracked_resource file("file");
    tracked_resource buffer("buffer");

    parse_payload(should_fail);

    std::printf("inner: success path, work_units=%d\n", work_units);
}

static NOINLINE void run_operation(const char *name, int should_fail)
{
    std::printf("-- %s --\n", name);

    work_units = 0;
    EH_BEGIN();

    run_inner(should_fail);

    if (eh_error != nullptr) {
        std::printf("operation: cleanup after destructors, code=%d, where=%s, message=%s, work_units=%d\n",
                    static_cast<int>(eh_error->code),
                    eh_error->where,
                    eh_error->message,
                    work_units);
        return;
    }

    std::printf("operation: success, work_units=%d\n", work_units);
}

int main()
{
    run_operation("c++ plugin raii success case", 0);
    run_operation("c++ plugin raii failure case", 1);
    return 0;
}
