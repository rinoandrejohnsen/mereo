#include "benchmark.h"

#include <inttypes.h>
#include <stdint.h>

#define CHECKS_PER_ITERATION UINT64_C(8)

typedef uint64_t (*branch_bench_fn)(uint64_t iterations, uintptr_t rcx_value);

static uint64_t bench_jrcxz(uint64_t iterations, uintptr_t rcx_value)
{
    uint64_t sink = 0;

    if (iterations == 0) {
        return 0;
    }

    __asm__ volatile(
        "mov %[iterations], %%rax\n\t"
        "mov %[rcx_value], %%rcx\n\t"
        "xor %%rdx, %%rdx\n\t"
        "1:\n\t"
        "jrcxz 2f\n\t"
        "add $1, %%rdx\n\t"
        "2:\n\t"
        "jrcxz 3f\n\t"
        "add $1, %%rdx\n\t"
        "3:\n\t"
        "jrcxz 4f\n\t"
        "add $1, %%rdx\n\t"
        "4:\n\t"
        "jrcxz 5f\n\t"
        "add $1, %%rdx\n\t"
        "5:\n\t"
        "jrcxz 6f\n\t"
        "add $1, %%rdx\n\t"
        "6:\n\t"
        "jrcxz 7f\n\t"
        "add $1, %%rdx\n\t"
        "7:\n\t"
        "jrcxz 8f\n\t"
        "add $1, %%rdx\n\t"
        "8:\n\t"
        "jrcxz 9f\n\t"
        "add $1, %%rdx\n\t"
        "9:\n\t"
        "dec %%rax\n\t"
        "jnz 1b\n\t"
        : "=&d"(sink)
        : [iterations] "r"(iterations),
          [rcx_value] "r"(rcx_value)
        : "rax", "rcx", "cc");

    return sink;
}

static uint64_t bench_test_jz(uint64_t iterations, uintptr_t rcx_value)
{
    uint64_t sink = 0;

    if (iterations == 0) {
        return 0;
    }

    __asm__ volatile(
        "mov %[iterations], %%rax\n\t"
        "mov %[rcx_value], %%rcx\n\t"
        "xor %%rdx, %%rdx\n\t"
        "1:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 2f\n\t"
        "add $1, %%rdx\n\t"
        "2:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 3f\n\t"
        "add $1, %%rdx\n\t"
        "3:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 4f\n\t"
        "add $1, %%rdx\n\t"
        "4:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 5f\n\t"
        "add $1, %%rdx\n\t"
        "5:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 6f\n\t"
        "add $1, %%rdx\n\t"
        "6:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 7f\n\t"
        "add $1, %%rdx\n\t"
        "7:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 8f\n\t"
        "add $1, %%rdx\n\t"
        "8:\n\t"
        "test %%rcx, %%rcx\n\t"
        "jz 9f\n\t"
        "add $1, %%rdx\n\t"
        "9:\n\t"
        "dec %%rax\n\t"
        "jnz 1b\n\t"
        : "=&d"(sink)
        : [iterations] "r"(iterations),
          [rcx_value] "r"(rcx_value)
        : "rax", "rcx", "cc");

    return sink;
}

static uint64_t bench_jecxz(uint64_t iterations, uintptr_t rcx_value)
{
    uint64_t sink = 0;

    if (iterations == 0) {
        return 0;
    }

    __asm__ volatile(
        "mov %[iterations], %%rax\n\t"
        "mov %[rcx_value], %%rcx\n\t"
        "xor %%rdx, %%rdx\n\t"
        "1:\n\t"
        "jecxz 2f\n\t"
        "add $1, %%rdx\n\t"
        "2:\n\t"
        "jecxz 3f\n\t"
        "add $1, %%rdx\n\t"
        "3:\n\t"
        "jecxz 4f\n\t"
        "add $1, %%rdx\n\t"
        "4:\n\t"
        "jecxz 5f\n\t"
        "add $1, %%rdx\n\t"
        "5:\n\t"
        "jecxz 6f\n\t"
        "add $1, %%rdx\n\t"
        "6:\n\t"
        "jecxz 7f\n\t"
        "add $1, %%rdx\n\t"
        "7:\n\t"
        "jecxz 8f\n\t"
        "add $1, %%rdx\n\t"
        "8:\n\t"
        "jecxz 9f\n\t"
        "add $1, %%rdx\n\t"
        "9:\n\t"
        "dec %%rax\n\t"
        "jnz 1b\n\t"
        : "=&d"(sink)
        : [iterations] "r"(iterations),
          [rcx_value] "r"(rcx_value)
        : "rax", "rcx", "cc");

    return sink;
}

static void run_branch_bench(
    const char *name,
    branch_bench_fn fn,
    uintptr_t rcx_value)
{
    const uint64_t iterations = BENCH_ITERATIONS;
    const uint64_t checks = iterations * CHECKS_PER_ITERATION;

    (void)fn(1024, rcx_value);

    uint64_t start = benchmark_now_ns();
    uint64_t sink = fn(iterations, rcx_value);
    uint64_t elapsed = benchmark_now_ns() - start;
    double ns_per_check = (double)elapsed / (double)checks;

    benchmark_sink ^= sink;

    printf("%-28s rcx=%" PRIuPTR " checks=%" PRIu64
           " sink=%" PRIu64 " time=%" PRIu64 " ns %.3f ns/check\n",
           name,
           rcx_value,
           checks,
           sink,
           elapsed,
           ns_per_check);
}

int main(void)
{
    puts("success-path shape: branch not taken when rcx != 0");
    run_branch_bench("jrcxz skip", bench_jrcxz, (uintptr_t)1);
    run_branch_bench("jecxz skip", bench_jecxz, (uintptr_t)1);
    run_branch_bench("test rcx,rcx; jz skip", bench_test_jz, (uintptr_t)1);

    puts("failure-path shape: branch taken when rcx == 0");
    run_branch_bench("jrcxz skip", bench_jrcxz, (uintptr_t)0);
    run_branch_bench("jecxz skip", bench_jecxz, (uintptr_t)0);
    run_branch_bench("test rcx,rcx; jz skip", bench_test_jz, (uintptr_t)0);

    return 0;
}
