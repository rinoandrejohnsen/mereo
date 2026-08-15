#include "benchmark.h"

#include <stdint.h>

/*
 * Strategy: return a compact status enum and write the value through an output
 * parameter. This is explicit, allocation-free, and a strong default for hot C
 * code where parse failures are expected and recoverable.
 */

typedef enum parse_status {
    PARSE_OK = 0,
    PARSE_EMPTY,
    PARSE_BAD_CHAR,
    PARSE_OVERFLOW,
} parse_status;

static const char *parse_status_name(parse_status status)
{
    switch (status) {
    case PARSE_OK:
        return "ok";
    case PARSE_EMPTY:
        return "empty";
    case PARSE_BAD_CHAR:
        return "bad char";
    case PARSE_OVERFLOW:
        return "overflow";
    }

    return "unknown";
}

static parse_status parse_u32_status(const char *text, uint32_t *out)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;

    if (unlikely(*p == '\0')) {
        return PARSE_EMPTY;
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            return PARSE_BAD_CHAR;
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            return PARSE_OVERFLOW;
        }

        value = value * 10u + digit;
        ++p;
    } while (*p != '\0');

    *out = value;
    return PARSE_OK;
}

int main(void)
{
    uint64_t ok = 0;
    uint64_t errors = 0;
    uint64_t sum = 0;
    uint64_t start = benchmark_now_ns();

    for (uint64_t i = 0; i < BENCH_ITERATIONS; ++i) {
        uint32_t value = 0;
        parse_status status = parse_u32_status(benchmark_rare_failure_input(i), &value);

        if (likely(status == PARSE_OK)) {
            sum += value;
            ++ok;
        } else {
            ++errors;
        }
    }

    benchmark_result result = {
        .name = "status enum + out parameter",
        .iterations = BENCH_ITERATIONS,
        .ok = ok,
        .errors = errors,
        .sum = sum,
        .elapsed_ns = benchmark_now_ns() - start,
    };
    benchmark_print(&result);

    {
        uint32_t value = 0;
        parse_status status = parse_u32_status("123x", &value);
        printf("demo: parse \"123x\" -> %s\n", parse_status_name(status));
    }

    return 0;
}
