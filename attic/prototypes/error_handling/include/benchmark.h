#ifndef ERROR_HANDLING_BENCHMARK_H
#define ERROR_HANDLING_BENCHMARK_H

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#ifndef BENCH_ITERATIONS
#define BENCH_ITERATIONS 8000000
#endif

#if defined(__GNUC__) || defined(__clang__)
#define likely(expr) __builtin_expect(!!(expr), 1)
#define unlikely(expr) __builtin_expect(!!(expr), 0)
#define cold_path __attribute__((cold))
#else
#define likely(expr) (expr)
#define unlikely(expr) (expr)
#define cold_path
#endif

typedef struct benchmark_result {
    const char *name;
    uint64_t iterations;
    uint64_t ok;
    uint64_t errors;
    uint64_t sum;
    uint64_t elapsed_ns;
} benchmark_result;

static volatile uint64_t benchmark_sink;

static inline uint64_t benchmark_now_ns(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        abort();
    }

    return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static inline const char *benchmark_success_input(uint64_t i)
{
    static const char *const inputs[] = {
        "0",
        "17",
        "65535",
        "1234567890",
        "4294967295",
        "31415926",
        "27182818",
        "4000000000",
    };

    return inputs[(size_t)(i & UINT64_C(7))];
}

static inline const char *benchmark_rare_failure_input(uint64_t i)
{
    static const char *const bad_inputs[] = {
        "",
        "not-a-number",
        "4294967296",
        "123x",
    };

    if (unlikely((i & UINT64_C(1023)) == UINT64_C(1023))) {
        return bad_inputs[(size_t)((i >> UINT64_C(10)) & UINT64_C(3))];
    }

    return benchmark_success_input(i);
}

static inline void benchmark_print(const benchmark_result *result)
{
    double ns_per_item = 0.0;

    if (result->iterations != 0) {
        ns_per_item = (double)result->elapsed_ns / (double)result->iterations;
    }

    benchmark_sink ^= result->sum + result->errors;

    printf("%-34s ok=%" PRIu64 " err=%" PRIu64
           " sum=%" PRIu64 " time=%" PRIu64 " ns %.2f ns/item\n",
           result->name,
           result->ok,
           result->errors,
           result->sum,
           result->elapsed_ns,
           ns_per_item);
}

#endif
