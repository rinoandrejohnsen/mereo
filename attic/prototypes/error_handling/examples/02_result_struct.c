#include "benchmark.h"

#include <stdint.h>

/*
 * Strategy: return a small result object containing both status and value.
 * On common ABIs this struct is returned in registers, while call sites avoid
 * a separate output parameter.
 */

typedef enum parse_status {
    PARSE_OK = 0,
    PARSE_EMPTY,
    PARSE_BAD_CHAR,
    PARSE_OVERFLOW,
} parse_status;

typedef struct parse_result {
    uint32_t value;
    parse_status status;
} parse_result;

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

static parse_result parse_u32_result(const char *text)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;

    if (unlikely(*p == '\0')) {
        return (parse_result){ .value = 0, .status = PARSE_EMPTY };
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            return (parse_result){ .value = 0, .status = PARSE_BAD_CHAR };
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            return (parse_result){ .value = 0, .status = PARSE_OVERFLOW };
        }

        value = value * 10u + digit;
        ++p;
    } while (*p != '\0');

    return (parse_result){ .value = value, .status = PARSE_OK };
}

int main(void)
{
    uint64_t ok = 0;
    uint64_t errors = 0;
    uint64_t sum = 0;
    uint64_t start = benchmark_now_ns();

    for (uint64_t i = 0; i < BENCH_ITERATIONS; ++i) {
        parse_result parsed = parse_u32_result(benchmark_rare_failure_input(i));

        if (likely(parsed.status == PARSE_OK)) {
            sum += parsed.value;
            ++ok;
        } else {
            ++errors;
        }
    }

    benchmark_result result = {
        .name = "returned result struct",
        .iterations = BENCH_ITERATIONS,
        .ok = ok,
        .errors = errors,
        .sum = sum,
        .elapsed_ns = benchmark_now_ns() - start,
    };
    benchmark_print(&result);

    {
        parse_result parsed = parse_u32_result("4294967296");
        printf("demo: parse \"4294967296\" -> %s\n", parse_status_name(parsed.status));
    }

    return 0;
}
