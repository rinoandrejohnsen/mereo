CC ?= cc
CXX ?= c++
BENCH_ITERATIONS ?= 8000000
GCC_PLUGIN_DIR ?= $(shell $(CC) -print-file-name=plugin)

CPPFLAGS ?=
CPPFLAGS += -Iinclude -DBENCH_ITERATIONS=$(BENCH_ITERATIONS)

CFLAGS ?= -O3 -std=c11 -Wall -Wextra -Wpedantic -DNDEBUG -D_POSIX_C_SOURCE=200809L
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic -DNDEBUG
PLUGIN_CXXFLAGS ?= -O2 -Wall -Wextra -fPIC -fno-rtti
LDFLAGS ?=

C_SOURCES := $(wildcard examples/*.c)
CXX_SOURCES := $(wildcard examples/*.cpp)
ASM_SOURCES := $(wildcard examples/*.S)
C_PROGRAMS := $(patsubst examples/%.c,build/%,$(C_SOURCES))
CXX_PROGRAMS := $(patsubst examples/%.cpp,build/%,$(CXX_SOURCES))
ASM_PROGRAMS := $(patsubst examples/%.S,build/%,$(ASM_SOURCES))
PROGRAMS := $(C_PROGRAMS) $(CXX_PROGRAMS) $(ASM_PROGRAMS)

.PHONY: all run clean

all: $(PROGRAMS)

run: all
	@set -e; \
	for program in $(PROGRAMS); do \
		echo "== $$program =="; \
		$$program; \
	done

build/%: examples/%.c include/benchmark.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@ $(LDFLAGS)

build/11_r15_reserved_status: CFLAGS += -ffixed-r15
build/12_test_jz_vs_jnz: CFLAGS += -ffixed-r15
build/13_plugin_autocheck: CFLAGS += -ffixed-r15 -Wno-pedantic -Wno-volatile-register-var

build/13_plugin_autocheck: examples/13_plugin_autocheck.c build/eh_autocheck.so include/benchmark.h | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -fplugin=./build/eh_autocheck.so $< -o $@ $(LDFLAGS)

build/14_cpp_raii_r15_manual: CXXFLAGS += -ffixed-r15 -fno-exceptions
build/15_cpp_plugin_raii_autoreturn: CXXFLAGS += -ffixed-r15 -fno-exceptions -Wno-register -Wno-volatile-register-var -Wno-pedantic
build/16_cpp_syscall_raii_r15: CXXFLAGS += -ffixed-r15 -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdinc++ -Wno-register -Wno-volatile-register-var -Wno-pedantic

build/15_cpp_plugin_raii_autoreturn: examples/15_cpp_plugin_raii_autoreturn.cpp build/eh_autocheck.so | build
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -fplugin=./build/eh_autocheck.so $< -o $@ $(LDFLAGS)

build/16_cpp_syscall_raii_r15: examples/16_cpp_syscall_raii_r15.cpp examples/dummy_input.txt build/eh_autocheck.so | build
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -fplugin=./build/eh_autocheck.so $< -o $@ -nostdlib -static -no-pie $(LDFLAGS)

build/%: examples/%.cpp | build
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $< -o $@ $(LDFLAGS)

build/%: examples/%.S | build
	$(CC) $(CPPFLAGS) $< -o $@ $(LDFLAGS)

build/eh_autocheck.so: gcc-plugin/eh_autocheck.cc | build
	$(CXX) $(PLUGIN_CXXFLAGS) -I$(GCC_PLUGIN_DIR)/include -shared $< -o $@

build:
	mkdir -p $@

clean:
	rm -rf build
