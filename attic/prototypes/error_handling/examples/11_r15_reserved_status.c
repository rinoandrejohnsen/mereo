#include <stdio.h>

/*
 * C-hosted custom ABI experiment:
 *
 *     r15 == NULL  means operation is still OK
 *     r15 != NULL  points to error metadata from somewhere below
 *
 * Build this file with -ffixed-r15. Without that, the compiler may use r15 as
 * an ordinary callee-saved register and restore the old "OK" value while the
 * call chain returns, losing the error state.
 */

typedef enum error_code {
    ERROR_NONE = 0,
    ERROR_DECODE_FAILED = 77,
} error_code;

typedef struct error_info {
    error_code code;
    const char *message;
    const char *where;
} error_info;

static const error_info decode_error = {
    .code = ERROR_DECODE_FAILED,
    .message = "decode failed",
    .where = "level3",
};

static volatile int work_units;

#define NOINLINE __attribute__((noinline))

#define EH_BEGIN() \
    __asm__ volatile("xor %%r15d, %%r15d" ::: "cc")

#define EH_RAISE(error_ptr)                                 \
    do {                                                    \
        const error_info *eh_error__ = (error_ptr);          \
        __asm__ volatile("mov %0, %%r15" :: "r"(eh_error__)); \
    } while (0)

#define EH_CHECK(cleanup_label)                             \
    __asm__ goto volatile(                                  \
        "test %%r15, %%r15\n\t"                             \
        "jnz %l0"                                           \
        :                                                   \
        :                                                   \
        : "cc"                                              \
        : cleanup_label)

#define EH_ERROR_PTR(out_ptr) \
    __asm__ volatile("mov %%r15, %0" : "=r"(out_ptr))

static NOINLINE void level3(int should_fail)
{
    ++work_units;

    if (should_fail) {
        EH_RAISE(&decode_error);
    }
}

static NOINLINE void level2(int should_fail)
{
    ++work_units;
    level3(should_fail);
}

static NOINLINE void level1(int should_fail)
{
    ++work_units;
    level2(should_fail);
}

static NOINLINE void run_case(const char *name, int should_fail)
{
    printf("-- %s --\n", name);

    work_units = 0;

    EH_BEGIN();

    /*
     * No if-statements here and no return-value propagation through level1,
     * level2, or level3. A deep function can clear r15 and return normally.
     */
    level1(should_fail);

    EH_CHECK(cleanup);

    printf("boundary: success, work_units=%d\n", work_units);
    return;

cleanup:
    {
        const error_info *error = NULL;

        EH_ERROR_PTR(error);
        printf("boundary: cleanup, code=%d, where=%s, message=%s, work_units=%d\n",
           error->code,
           error->where,
           error->message,
           work_units);
    }
}

int main(void)
{
    run_case("r15 success case", 0);
    run_case("r15 failure case", 1);
    return 0;
}
