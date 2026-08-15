# Error Handling Experiments

Small C, C++, and x86-64 Linux experiments for low-overhead error handling.
The current main idea is a custom ABI where `r15` is reserved as an error
status register.

## Current Shape

- Syscall wrappers latch raw negative Linux errno values in `r15` with
  `test rax, rax; cmovs r15, rax`.
- Callers check `r15` at continuation/ownership boundaries.
- In C++, the GCC plugin can inject early `return` checks before RAII cleanup is
  lowered, so destructors run without exceptions.
- The smallest syscall example uses `_start`, raw syscalls, no libc, no C++
  runtime, and exits with `-r15`.

## Build

Build everything:

```sh
make
```

Build only the GCC plugin:

```sh
make build/eh_autocheck.so
```

Build the freestanding syscall/RAII example:

```sh
make build/16_cpp_syscall_raii_r15
```

Run all examples:

```sh
make run
```

Use a smaller benchmark size while iterating:

```sh
make run BENCH_ITERATIONS=1000000
```

## Important Files

- `gcc-plugin/eh_autocheck.cc`: GCC plugin that provides `eh_autocheck` and
  `eh_autoreturn`.
- `examples/13_plugin_autocheck.c`: C cleanup-label plugin example.
- `examples/15_cpp_plugin_raii_autoreturn.cpp`: C++ RAII/plugin example.
- `examples/16_cpp_syscall_raii_r15.cpp`: freestanding Linux x86-64 syscall
  example using `_start`, `r15`, RAII cleanup, and no libc/C++ runtime.

## Compiler Plugin

The plugin is built as:

```sh
build/eh_autocheck.so
```

and loaded with:

```sh
-fplugin=./build/eh_autocheck.so
```

Participating code must reserve `r15`:

```sh
-ffixed-r15
```

Attributes:

- `eh_autocheck`: C-oriented pass that injects checks after calls and branches
  to a fixed cleanup label or marker.
- `eh_autoreturn`: C++-oriented pass for `void` functions that injects
  `if (eh_error != 0) return;` after call statements early enough for normal
  C++ destructors to run.

This is a proof of concept, not a hardened language extension.

## Example Map

- `01` to `06`: baseline C strategies and benchmark comparisons.
- `07`: coroutine interrupt/cleanup sketch.
- `08` and `09`: assembly continuation/status-register sketches.
- `10` and `12`: branch-shape microbenchmarks.
- `11`: C-hosted reserved-`r15` status example.
- `13`: C plugin auto-check example.
- `14` and `15`: C++ RAII with manual/plugin checks.
- `16`: freestanding syscall/RAII target.
