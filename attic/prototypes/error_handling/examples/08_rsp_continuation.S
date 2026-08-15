/*
 * x86-64 SysV proof-of-concept:
 *
 *     rsp = choose_continuation(...);
 *     ret;
 *
 * The chosen stack pointer points at a fake return address. If the callee
 * reports success, that fake return address is the normal continuation. If it
 * reports failure, the fake return address is the cleanup continuation.
 *
 * This is not a normal C ABI technique. It is a small custom-ABI experiment
 * showing how "return the next instruction" can be modeled with rsp + ret.
 */

.intel_syntax noprefix

.section .rodata
case_success:
    .string "-- success case --"
case_failure:
    .string "-- failure case --"
normal_path:
    .string "normal continuation: work succeeded"
cleanup_path:
    .string "cleanup continuation: error=%d, cleaning up\n"

.text

.globl main
.type main, @function
main:
    push rbp
    mov rbp, rsp
    sub rsp, 16

    lea rdi, [rip + case_success]
    call puts@PLT
    xor edi, edi
    call run_case

    lea rdi, [rip + case_failure]
    call puts@PLT
    mov edi, 1
    call run_case

    xor eax, eax
    leave
    ret
.size main, .-main

/*
 * run_case(should_fail)
 *
 * Builds two fake one-entry stacks:
 *
 *     success_sp -> success_continuation
 *     cleanup_sp -> cleanup_continuation
 *
 * Then asks choose_continuation() which stack to use.
 */
.type run_case, @function
run_case:
    push rbp
    mov rbp, rsp
    sub rsp, 64

    lea rax, [rip + .Lsuccess_continuation]
    mov QWORD PTR [rbp - 8], rax

    lea rax, [rip + .Lcleanup_continuation]
    mov QWORD PTR [rbp - 24], rax

    /*
     * Custom calling convention for choose_continuation:
     *   edi = should_fail
     *   rsi = success stack pointer
     *   rdx = cleanup stack pointer
     *
     * Returns:
     *   rax = selected stack pointer
     *   edi = 0 on success, error code on failure
     */
    lea rsi, [rbp - 8]
    lea rdx, [rbp - 24]
    call choose_continuation

    /*
     * This is the experiment:
     *
     *   rsp = choose_continuation(...);
     *   ret;
     *
     * ret pops the fake return address from the selected stack and transfers
     * control to either .Lsuccess_continuation or .Lcleanup_continuation.
     */
    mov rsp, rax
    ret

.Lsuccess_continuation:
    lea rdi, [rip + normal_path]
    call puts@PLT
    leave
    ret

.Lcleanup_continuation:
    mov esi, edi
    lea rdi, [rip + cleanup_path]
    xor eax, eax
    call printf@PLT
    leave
    ret
.size run_case, .-run_case

/*
 * choose_continuation(should_fail, success_sp, cleanup_sp)
 *
 * This function is deliberately tiny: no caller-side error branch is needed
 * after it returns. It chooses the continuation stack instead.
 */
.type choose_continuation, @function
choose_continuation:
    test edi, edi
    jne .Lchoose_failure

    mov rax, rsi
    xor edi, edi
    ret

.Lchoose_failure:
    mov rax, rdx
    mov edi, 77
    ret
.size choose_continuation, .-choose_continuation

.section .note.GNU-stack,"",@progbits
