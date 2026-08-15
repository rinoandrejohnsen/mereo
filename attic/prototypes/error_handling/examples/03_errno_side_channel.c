#include "benchmark.h"

#include <errno.h>
#include <stdint.h>
#include <string.h>

/*
 * Strategy: return 0/-1 and put the detail in errno, like many libc APIs.
 * This is familiar, but errno is thread-local state and should usually stay on
 * the cold failure path rather than being touched on success.
 */

static cold_path int parse_fail(int error_number)
{
    errno = error_number;
    return -1;
}

static int parse_u32_errno(const char *text, uint32_t *out)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;

    if (unlikely(*p == '\0')) {
        return parse_fail(EINVAL);
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            return parse_fail(EILSEQ);
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            return parse_fail(ERANGE);
        }

        value = value * 10u + digit;
        ++p;
    } while (*p != '\0');

    *out = value;
    return 0;
}

int main(void)
{
    uint64_t ok = 0;
    uint64_t errors = 0;
    uint64_t sum = 0;
    uint64_t start = benchmark_now_ns();

    for (uint64_t i = 0; i < BENCH_ITERATIONS; ++i) {
        uint32_t value = 0;

        if (likely(parse_u32_errno(benchmark_rare_failure_input(i), &value) == 0)) {
            sum += value;
            ++ok;
        } else {
            ++errors;
        }
    }

    benchmark_result result = {
        .name = "errno side channel",
        .iterations = BENCH_ITERATIONS,
        .ok = ok,
        .errors = errors,
        .sum = sum,
        .elapsed_ns = benchmark_now_ns() - start,
    };
    benchmark_print(&result);

    {
        uint32_t value = 0;

        if (parse_u32_errno("4294967296", &value) != 0) {
            printf("demo: parse \"4294967296\" -> errno=%d (%s)\n",
                   errno,
                   strerror(errno));
        }
    }

    return 0;
}
