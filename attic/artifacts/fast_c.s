	.file	"fast.c"
	.text
	.section	.rodata.str1.1,"aMS",@progbits,1
.LC0:
	.string	"lorem_ipsum.txt"
	.text
	.p2align 4
	.globl	_start
	.type	_start, @function
_start:
	movl	$2, %eax
	leaq	.LC0(%rip), %rdi
	xorl	%esi, %esi
#APP
# 6 "fast.c" 1
	syscall
# 0 "" 2
#NO_APP
	movq	%rax, %r8
	testq	%rax, %rax
	js	.L4
	movq	%rsi, %rax
	movq	%r8, %rdi
	movl	$4096, %edx
	leaq	buffer(%rip), %rsi
#APP
# 7 "fast.c" 1
	syscall
# 0 "" 2
#NO_APP
	movq	%rax, %rdx
	testq	%rax, %rax
	js	.L5
	movl	$1, %eax
	movq	%rax, %rdi
#APP
# 7 "fast.c" 1
	syscall
# 0 "" 2
#NO_APP
	sarq	$63, %rax
	andq	$-3, %rax
	movq	%rax, %rdx
.L3:
	movl	$3, %eax
	movq	%r8, %rdi
#APP
# 5 "fast.c" 1
	syscall
# 0 "" 2
#NO_APP
.L2:
	movl	$60, %eax
	movq	%rdx, %rdi
#APP
# 5 "fast.c" 1
	syscall
# 0 "" 2
#NO_APP
.L4:
	movq	$-1, %rdx
	jmp	.L2
.L5:
	movq	$-2, %rdx
	jmp	.L3
	.size	_start, .-_start
	.globl	buffer
	.bss
	.align 32
	.type	buffer, @object
	.size	buffer, 4096
buffer:
	.zero	4096
	.ident	"GCC: (GNU) 16.1.1 20260430"
	.section	.note.GNU-stack,"",@progbits
