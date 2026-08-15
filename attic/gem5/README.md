# gem5 — a simulated Raptor Cove P-core

`raptorcove.py` models ONE P-core of this host (Intel i9-13900K) in gem5's
syscall-emulation mode, so a mereo binary can be measured without the
P-core/E-core migration noise that makes wall-clock useless here.

    export LD_LIBRARY_PATH=/tmp/py311/usr/lib PYTHONHOME=/tmp/py311/usr
    /home/rino/gem5/build/X86/gem5.opt --outdir=OUT gem5/raptorcove.py \
        --cmd=$PWD/build/jsondemo

`--cpu=` selects `o3` (default, the modelled P-core), `stock` (gem5's default
O3), `stock+iq`, `timing` or `atomic`. `--no-caches` reproduces what gem5's own
`se.py` does by default.

`bench/run.sh` builds and measures the packed-vs-normal benchmarks on real
hardware; `bench/run.sh --gem5` adds the simulated column.

## How far to trust it

**Instruction counts: good.** jsondemo simulates 441 instructions against 449
measured by `perf` — 1.8% apart, the difference being `rt_sigaction`, which SE
mode ignores. Comparisons of *work done* are sound.

**Cycle counts: NOT calibrated, and not calibratable by a constant.**

| workload | gem5 / real |
|---|---|
| tiny_normal | 2.31x |
| vec_packed | 3.29x |
| vec_normal | 4.32x |
| tiny_packed | 5.59x |
| asmall_normal | 5.94x |
| small_normal | 7.46x |
| small_packed | 7.99x |
| large_normal | 10.66x |
| large_packed | 12.42x |

Mean 6.66x, spread 2.31x-12.42x. The error is not a scale factor: it correlates
with *split memory accesses*, so it is worst exactly where a layout question is
being asked.

**It gets one comparison backwards.** On the `tiny` pair (both layouts resident
in L1, so footprint cannot matter) gem5 says packed is +136.9% slower; the real
CPU says -1.9%, i.e. no difference. Raptor Cove absorbs unaligned access at full
speed and gem5 does not model that.

So: use it for instruction counts and for coarse relative comparisons of aligned
code. Do NOT use it to answer alignment or packing questions — measure those with
`perf stat -e cycles:u -r 7` pinned via `taskset -c 0`.

## Where the model knowingly departs from the hardware

Cache sizes, associativity and line size are taken verbatim from
`/sys/devices/system/cpu/cpu0/cache/index*`, so those are exact. The rest:

- **No uop cache.** Raptor Cove's 4096-uop DSB sustains 8 uops/cycle. gem5 has no
  such structure, so the front end is modelled at its *sustained* width (8), not
  the legacy decoder width (6). Setting 6 here made the model 2x slower than
  gem5's own defaults — a real bug that was in this file and is now fixed.
- **L3 associativity is 9, not 12.** Capacity is exact at 36 MiB. The real cache
  is 12-way built from 12 slices of 3 MiB (4096 sets each, a power of two);
  modelled as one cache, 36 MiB/12-way needs 49152 sets, which gem5's indexing
  policies reject. 36 MiB admits only 9-, 18- or 36-way; 9 is nearest.
- **BTB associativity is 6.** 12288 entries is the published figure, and gem5
  indexes the BTB like a cache, so entries/assoc must be a power of two.
- **Branch predictor is TAGE-SC-L 64KB**, a published design of similar class.
  Intel does not disclose theirs.

## Two traps that cost real time

- `fetchBufferSize` is the fetch buffer in BYTES, and gem5's default is 64.
  Setting it to 32 (reasoning "32 B/cycle from L1i") halves fetch bandwidth and
  cost 2.2x on a front-end-bound loop.
- Every front-end stage was set to the 6-wide decode figure. Allocation is
  8-wide; the model must reflect the sustained rate, not the narrowest stage.

Both were found by sanity-checking the "better" config against gem5's stock
defaults on a known workload. **Do that first** after any parameter change: if a
wider machine is slower than stock, the config is wrong, not the workload.

## Build notes

gem5 does not build against this host's toolchain: GCC 16.1.1 and clang 22.1.8
are both outside its supported ranges, and Python 3.14 makes its bundled pybind11
ICE *any* compiler (three different ones failed, each on a different file — the
common factor is pybind11, not the compiler).

It was built with a local toolchain extracted under `/tmp`, no root required:

    gcc 14.3.1     /tmp/gcc14      (CachyOS package, extracted)
    Python 3.11.14 /tmp/py311      (ditto; PYTHONHOME must point at it)
    scons          /tmp/scons311
    shims          /tmp/gem5cc     (gcc/g++/python3 -> the above)
    PROTOC=/nonexistent            (a stale protobuf 3.9.1 in /usr/local
                                    shadows the system 35.1 and breaks the link)

One line was patched in the gem5 tree: `PYTHONHOME` added to the environment
passthrough in `site_scons/gem5_scons/defaults.py`.

**`/tmp` does not survive a reboot.** To make this durable:
`sudo pacman -S python311 gcc14`, then drop the `PYTHONHOME`/`LD_LIBRARY_PATH`
exports. Deleting the stale `/usr/local` protobuf would also let tracing build.
