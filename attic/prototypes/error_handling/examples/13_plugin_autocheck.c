#include <stdio.h>

typedef enum error_code {
    ERROR_DECODE_FAILED = 77,
} error_code;

typedef struct error_info {
    error_code code;
    const char *message;
    const char *where;
} error_info;

register const error_info * volatile eh_error __asm__("r15");

static const error_info decode_error = {
    .code = ERROR_DECODE_FAILED,
    .message = "decode failed",
    .where = "leaf_decode",
};

static volatile int work_units;

#define NOINLINE __attribute__((noinline))

#define EH_BEGIN() \
    do { eh_error = 0; } while (0)

#define EH_RAISE(error_ptr)                                  \
    do { eh_error = (error_ptr); } while (0)

static NOINLINE void eh_cleanup_marker(void)
{
}

static NOINLINE void leaf_decode(int should_fail)
{
    ++work_units;

    if (should_fail) {
        EH_RAISE(&decode_error);
    }
}

static NOINLINE void parse_payload(int should_fail)
{
    ++work_units;
    leaf_decode(should_fail);
}

static NOINLINE void read_payload(int should_fail)
{
    ++work_units;
    parse_payload(should_fail);
}

__attribute__((noinline, eh_autocheck))
static void run_operation(const char *name, int should_fail)
{
    EH_BEGIN();

    printf("-- %s --\n", name);

    work_units = 0;

    read_payload(should_fail);

    /*
     * There is intentionally no EH_CHECK here. The plugin inserts a check
     * after the call above and branches to eh_cleanup when eh_error != NULL.
     * This conditional keeps the label visible to GCC before the plugin pass.
     */
    if (should_fail < 0) {
        goto eh_cleanup;
    }

    printf("operation: success, work_units=%d\n", work_units);
    return;

eh_cleanup:
    eh_cleanup_marker();
    printf("operation: cleanup, code=%d, where=%s, message=%s, work_units=%d\n",
           eh_error->code,
           eh_error->where,
           eh_error->message,
           work_units);
}

int main(void)
{
    run_operation("plugin success case", 0);
    run_operation("plugin failure case", 1);
    return 0;
}
