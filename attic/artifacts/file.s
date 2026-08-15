	.file	"file.cpp"
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
# 7 "file.cpp" 1
	syscall
# 0 "" 2
#NO_APP
	movl	$1, %r8d
	movq	%rax, %r9
	testq	%rax, %rax
	js	.L2
	movq	%rsi, %rax
	movq	%r9, %rdi
	movl	$4096, %edx
	leaq	buffer(%rip), %rsi
#APP
# 8 "file.cpp" 1
	syscall
# 0 "" 2
#NO_APP
	movq	%rax, %rdx
	testq	%rax, %rax
	js	.L5
	movq	%r8, %rax
	movq	%r8, %rdi
#APP
# 8 "file.cpp" 1
	syscall
# 0 "" 2
#NO_APP
	movq	%rax, %r8
	sarq	$63, %r8
	andl	$3, %r8d
.L3:
	movl	$3, %eax
	movq	%r9, %rdi
#APP
# 6 "file.cpp" 1
	syscall
# 0 "" 2
#NO_APP
.L2:
	movq	%r8, %rdi
	movl	$60, %eax
	negq	%rdi
#APP
# 6 "file.cpp" 1
	syscall
# 0 "" 2
#NO_APP
.L5:
	movl	$2, %r8d
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
