#include "benchmark.h"

#include <setjmp.h>
#include <stdint.h>

/*
 * Strategy: abort a whole operation with setjmp/longjmp. This can remove
 * repeated call-site checks for "cannot continue" failures, but it is a poor
 * fit for ordinary per-item validation because recovery jumps out of the loop.
 */

typedef enum parse_status {
    PARSE_OK = 0,
    PARSE_EMPTY,
    PARSE_BAD_CHAR,
    PARSE_OVERFLOW,
} parse_status;

static jmp_buf parse_jump;
static parse_status last_error;

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

static cold_path void raise_parse_error(parse_status status)
{
    last_error = status;
    longjmp(parse_jump, 1);
}

static uint32_t parse_u32_or_jump(const char *text)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;

    if (unlikely(*p == '\0')) {
        raise_parse_error(PARSE_EMPTY);
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            raise_parse_error(PARSE_BAD_CHAR);
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            raise_parse_error(PARSE_OVERFLOW);
        }

        value = value * 10u + digit;
        ++p;
    } while (*p != '\0');

    return value;
}

int main(void)
{
    if (setjmp(parse_jump) == 0) {
        uint64_t ok = 0;
        uint64_t sum = 0;
        uint64_t start = benchmark_now_ns();

        for (uint64_t i = 0; i < BENCH_ITERATIONS; ++i) {
            sum += parse_u32_or_jump(benchmark_success_input(i));
            ++ok;
        }

        benchmark_result result = {
            .name = "setjmp boundary, success batch",
            .iterations = BENCH_ITERATIONS,
            .ok = ok,
            .errors = 0,
            .sum = sum,
            .elapsed_ns = benchmark_now_ns() - start,
        };
        benchmark_print(&result);
    } else {
        printf("benchmark aborted unexpectedly: %s\n", parse_status_name(last_error));
        return 1;
    }

    if (setjmp(parse_jump) == 0) {
        (void)parse_u32_or_jump("123x");
        printf("demo: unexpected success\n");
    } else {
        printf("demo: parse \"123x\" jumped -> %s\n", parse_status_name(last_error));
    }

    return 0;
}
