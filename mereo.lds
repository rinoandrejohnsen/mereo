/* mereo.lds -- the layout of a mereo binary.
 *
 * A mereo program is freestanding: one entry point, one code section, its
 * literals, and whatever `in static` asked for. The linker's built-in script is
 * written for a C program with a loader, constructors, unwind tables and a
 * dynamic section, and it pays for those in page-aligned segments the program
 * never fills -- a 2.6 KB `whoami` shipped as 9.5 KB of file. This says what is
 * actually there instead.
 *
 * The segments are left to the linker rather than declared with PHDRS, because
 * what it derives is exactly right: ONE read+execute segment for a program with
 * no static storage, and a second read+write one only when `in static` put
 * something in .bss. A declared PHDRS block emits every segment it names, so a
 * program with no .bss carried an empty PT_LOAD at address 0.
 *
 * DISCARDED, and why each is safe to drop:
 *   .eh_frame            unwind tables. mereo does not unwind -- its cleanup is
 *                        the derived release tower, which is ordinary jumps.
 *   .note.gnu.property   x86 CET feature bits, from the assembler. Dropping the
 *                        note means the kernel does not turn CET on; there are
 *                        no indirect calls in a mereo binary to protect.
 *   .note.gnu.build-id   a hash for a symbol server there isn't one of.
 *   .comment             the compiler's version string.
 *
 * Debug sections are NOT listed, so they are kept: build.sh links a second
 * binary with -g through this same script, and mereocheck and mereodis read
 * DWARF out of that one. Keeping both on one layout is the point -- the
 * layout that gets verified has to be the layout that ships.
 *
 * It wants three link flags to do its job (build.sh passes them):
 *   -Wl,-z,noseparate-code   do not split the headers into a segment of their
 *                            own; there is nothing to separate code FROM here
 *   -Wl,--build-id=none      or the linker warns that the note was discarded
 *   -s                       no symbol table in the shipped binary
 */

ENTRY(_start)

SECTIONS
{
    /* The headers live in the mapped image, so the first byte of code follows
       them directly instead of starting a page of its own. */
    . = 0x400000 + SIZEOF_HEADERS;

    .text : ALIGN(16) {
        *(.text.startup .text .text.*)
    }

    .rodata : ALIGN(16) {
        *(.rodata .rodata.*)
    }

    /* Writable storage moves to its own page in MEMORY but stays contiguous in
       the FILE -- the usual congruence trick. mereo has no initialised static
       data, so only .bss lands here and the file grows by nothing at all. */
    . = ALIGN(CONSTANT(MAXPAGESIZE)) + (. & (CONSTANT(MAXPAGESIZE) - 1));

    .data : { *(.data .data.*) }
    .bss  : { *(.bss .bss.* COMMON) }

    /DISCARD/ : {
        *(.eh_frame*)
        *(.note.*)
        *(.comment)
    }
}
