#include "benchmark.h"

#include <inttypes.h>
#include <stdint.h>
#include <stddef.h>

/*
 * Strategy: return a compact status in all cases and optionally fill rich
 * diagnostics. Hot callers pass NULL; debugging or boundary callers ask for
 * offset, offending byte, and partial value.
 */

typedef enum parse_status {
    PARSE_OK = 0,
    PARSE_EMPTY,
    PARSE_BAD_CHAR,
    PARSE_OVERFLOW,
} parse_status;

typedef struct parse_error {
    parse_status status;
    size_t offset;
    unsigned char byte;
    uint32_t partial_value;
} parse_error;

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

static cold_path parse_status fill_parse_error(
    parse_error *error,
    parse_status status,
    size_t offset,
    unsigned char byte,
    uint32_t partial_value)
{
    if (error != NULL) {
        *error = (parse_error){
            .status = status,
            .offset = offset,
            .byte = byte,
            .partial_value = partial_value,
        };
    }

    return status;
}

static parse_status parse_u32_with_context(
    const char *text,
    uint32_t *out,
    parse_error *error)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;
    size_t offset = 0;

    if (unlikely(*p == '\0')) {
        return fill_parse_error(error, PARSE_EMPTY, 0, '\0', 0);
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            return fill_parse_error(error, PARSE_BAD_CHAR, offset, *p, value);
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            return fill_parse_error(error, PARSE_OVERFLOW, offset, *p, value);
        }

        value = value * 10u + digit;
        ++p;
        ++offset;
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

        if (likely(parse_u32_with_context(
                       benchmark_rare_failure_input(i),
                       &value,
                       NULL) == PARSE_OK)) {
            sum += value;
            ++ok;
        } else {
            ++errors;
        }
    }

    benchmark_result result = {
        .name = "optional rich context",
        .iterations = BENCH_ITERATIONS,
        .ok = ok,
        .errors = errors,
        .sum = sum,
        .elapsed_ns = benchmark_now_ns() - start,
    };
    benchmark_print(&result);

    {
        uint32_t value = 0;
        parse_error error = { 0 };
        parse_status status = parse_u32_with_context("123x", &value, &error);

        printf("demo: parse \"123x\" -> %s at offset=%zu byte=0x%02x partial=%" PRIu32 "\n",
               parse_status_name(status),
               error.offset,
               (unsigned)error.byte,
               error.partial_value);
    }

    return 0;
}
