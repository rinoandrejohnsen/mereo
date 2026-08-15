#include "benchmark.h"

#include <inttypes.h>
#include <stdint.h>

#define CHECKS_PER_ITERATION UINT64_C(8)

typedef uint64_t (*branch_bench_fn)(uint64_t iterations, uintptr_t status);

static uint64_t bench_test_jz(uint64_t iterations, uintptr_t status)
{
    uint64_t sink = 0;

    if (iterations == 0) {
        return 0;
    }

    __asm__ volatile(
        "mov %[iterations], %%rax\n\t"
        "mov %[status], %%r15\n\t"
        "xor %%rdx, %%rdx\n\t"
        "1:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 2f\n\t"
        "add $1, %%rdx\n\t"
        "2:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 3f\n\t"
        "add $1, %%rdx\n\t"
        "3:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 4f\n\t"
        "add $1, %%rdx\n\t"
        "4:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 5f\n\t"
        "add $1, %%rdx\n\t"
        "5:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 6f\n\t"
        "add $1, %%rdx\n\t"
        "6:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 7f\n\t"
        "add $1, %%rdx\n\t"
        "7:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 8f\n\t"
        "add $1, %%rdx\n\t"
        "8:\n\t"
        "test %%r15, %%r15\n\t"
        "jz 9f\n\t"
        "add $1, %%rdx\n\t"
        "9:\n\t"
        "dec %%rax\n\t"
        "jnz 1b\n\t"
        : "=&d"(sink)
        : [iterations] "r"(iterations),
          [status] "r"(status)
        : "rax", "r15", "cc");

    return sink;
}

static uint64_t bench_test_jnz(uint64_t iterations, uintptr_t status)
{
    uint64_t sink = 0;

    if (iterations == 0) {
        return 0;
    }

    __asm__ volatile(
        "mov %[iterations], %%rax\n\t"
        "mov %[status], %%r15\n\t"
        "xor %%rdx, %%rdx\n\t"
        "1:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 2f\n\t"
        "add $1, %%rdx\n\t"
        "2:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 3f\n\t"
        "add $1, %%rdx\n\t"
        "3:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 4f\n\t"
        "add $1, %%rdx\n\t"
        "4:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 5f\n\t"
        "add $1, %%rdx\n\t"
        "5:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 6f\n\t"
        "add $1, %%rdx\n\t"
        "6:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 7f\n\t"
        "add $1, %%rdx\n\t"
        "7:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 8f\n\t"
        "add $1, %%rdx\n\t"
        "8:\n\t"
        "test %%r15, %%r15\n\t"
        "jnz 9f\n\t"
        "add $1, %%rdx\n\t"
        "9:\n\t"
        "dec %%rax\n\t"
        "jnz 1b\n\t"
        : "=&d"(sink)
        : [iterations] "r"(iterations),
          [status] "r"(status)
        : "rax", "r15", "cc");

    return sink;
}

static void run_branch_bench(
    const char *name,
    branch_bench_fn fn,
    uintptr_t status)
{
    const uint64_t iterations = BENCH_ITERATIONS;
    const uint64_t checks = iterations * CHECKS_PER_ITERATION;

    (void)fn(1024, status);

    uint64_t start = benchmark_now_ns();
    uint64_t sink = fn(iterations, status);
    uint64_t elapsed = benchmark_now_ns() - start;
    double ns_per_check = (double)elapsed / (double)checks;

    benchmark_sink ^= sink;

    printf("%-34s status=%" PRIuPTR " checks=%" PRIu64
           " sink=%" PRIu64 " time=%" PRIu64 " ns %.3f ns/check\n",
           name,
           status,
           checks,
           sink,
           elapsed,
           ns_per_check);
}

int main(void)
{
    puts("success path: branch not taken");
    run_branch_bench("test r15,r15; jz  cleanup", bench_test_jz, (uintptr_t)1);
    run_branch_bench("test r15,r15; jnz cleanup", bench_test_jnz, (uintptr_t)0);

    puts("failure path: branch taken");
    run_branch_bench("test r15,r15; jz  cleanup", bench_test_jz, (uintptr_t)0);
    run_branch_bench("test r15,r15; jnz cleanup", bench_test_jnz, (uintptr_t)1);

    return 0;
}
