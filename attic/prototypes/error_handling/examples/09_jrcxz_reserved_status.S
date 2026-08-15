/*
 * x86-64 SysV proof-of-concept:
 *
 *     rcx != 0  means operation is still OK
 *     rcx == 0  means an error was raised somewhere below
 *
 * The boundary does:
 *
 *     call level1
 *     jrcxz cleanup
 *
 * The deep function can set rcx=0 and return normally. The intermediate
 * functions do not inspect or propagate any status value; under this custom ABI
 * they simply must not clobber rcx.
 *
 * This demonstrates a cheaper local boundary than return-value plumbing. In a
 * real system, every participating object file would need to reserve rcx, and
 * calls into normal ABI code would need wrappers because ordinary callees may
 * freely clobber rcx.
 */

.intel_syntax noprefix

.section .rodata
case_success:
    .string "-- jrcxz success case --"
case_failure:
    .string "-- jrcxz failure case --"
success_path:
    .string "boundary: success fall-through"
cleanup_path:
    .string "boundary: jrcxz jumped to cleanup, error=%d\n"

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
 * edi = should_fail on entry
 *
 * Custom ABI inside the operation:
 *   rcx = nonzero while OK
 *   rcx = zero when failed
 *   edi = error code if failed
 */
.type run_case, @function
run_case:
    push rbp
    mov rbp, rsp

    mov ecx, 1
    call level1

    jrcxz .Lcleanup

    lea rdi, [rip + success_path]
    call puts@PLT
    leave
    ret

.Lcleanup:
    mov esi, edi
    lea rdi, [rip + cleanup_path]
    xor eax, eax
    call printf@PLT
    leave
    ret
.size run_case, .-run_case

/*
 * The middle of the call chain does no error checking and no status plumbing.
 * These functions preserve rcx only because they are written for this custom
 * ABI and contain only call/ret.
 */
.type level1, @function
level1:
    call level2
    ret
.size level1, .-level1

.type level2, @function
level2:
    call level3
    ret
.size level2, .-level2

/*
 * level3(should_fail)
 *
 * If it fails, it sets the reserved status register to zero and leaves an error
 * code in edi. It still returns normally; the boundary performs the collapse
 * check with jrcxz.
 */
.type level3, @function
level3:
    test edi, edi
    jne .Lfail
    ret

.Lfail:
    xor ecx, ecx
    mov edi, 77
    ret
.size level3, .-level3

.section .note.GNU-stack,"",@progbits
