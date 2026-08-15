# raptorcove.py -- a gem5 SE-mode model of ONE Raptor Cove P-core, as found on
# this host (Intel Core i9-13900K, 13th gen).
#
#   build/X86/gem5.opt raptorcove.py --cmd=<static binary> [--args=...]
#
# Cache geometry is taken VERBATIM from the host's own sysfs
# (/sys/devices/system/cpu/cpu0/cache/index*), so sizes, associativity and line
# size are equal by construction rather than by recollection:
#
#   L1i  32 KiB   8-way   64 B line
#   L1d  48 KiB  12-way   64 B line
#   L2    2 MiB  16-way   64 B line      (private, per P-core)
#   L3   36 MiB  12-way   64 B line      (shared on the real part; the single
#                                         simulated core gets all of it)
#
# Core width/depth figures are the published Golden/Raptor Cove numbers. What
# gem5's O3 model CANNOT represent is noted at each site -- see the README.

import argparse

import m5
from m5.objects import *

# ---------------------------------------------------------------- host figures
CLOCK = "5.8GHz"  # i9-13900K P-core max turbo (host reports 5.9 GHz TVB peak)
LINE = 64

# Measured load-to-use latencies for this microarchitecture, in core cycles.
# gem5 splits a cache access into tag + data + response, so each is a share of
# the total rather than the total itself.
L1D_TOTAL, L1I_TOTAL, L2_TOTAL, L3_TOTAL = 5, 4, 16, 50


class L1I(Cache):
    size, assoc = "32KiB", 8
    tag_latency, data_latency, response_latency = 1, L1I_TOTAL - 1, 1
    mshrs, tgts_per_mshr = 16, 8
    writeback_clean = True


class L1D(Cache):
    size, assoc = "48KiB", 12
    tag_latency, data_latency, response_latency = 1, L1D_TOTAL - 1, 1
    # Golden Cove sustains 3 loads + 2 stores per cycle; the MSHR count is the
    # closest gem5 knob to its ~16 outstanding L1 misses.
    mshrs, tgts_per_mshr = 16, 8
    writeback_clean = True


class L2(Cache):
    size, assoc = "2MiB", 16
    tag_latency, data_latency, response_latency = 4, L2_TOTAL - 5, 1
    mshrs, tgts_per_mshr = 32, 12
    writeback_clean = True


class L3(Cache):
    # CAPACITY IS EXACT; ASSOCIATIVITY IS NOT, and it cannot be. The real L3 is
    # 36 MiB 12-way, built as 12 slices of 3 MiB -- each slice is 12-way with
    # 4096 sets, a power of two. gem5 models the L3 as ONE cache, and
    # 36 MiB / 12-way / 64 B = 49152 sets, which its indexing policies reject
    # (both SetAssociative and SkewedAssociative require a power of two).
    # 36 MiB admits only 9-, 18- or 36-way under that constraint; 9 is nearest
    # to 12, so the miss-rate-dominant property (capacity) is held exact and the
    # conflict-behaviour property (associativity) is slightly pessimistic.
    size, assoc = "36MiB", 9
    tag_latency, data_latency, response_latency = 12, L3_TOTAL - 14, 2
    mshrs, tgts_per_mshr = 64, 16


def raptor_cove_core(model="o3"):
    """One P-core's out-of-order engine, sized to Raptor Cove.

    `model` may be "timing" or "atomic" to substitute gem5's IN-ORDER simple
    CPUs instead -- useful only for showing what they do differently, since
    neither can overlap a split memory access the way a real core does."""
    if model == "timing":
        return X86TimingSimpleCPU()
    if model == "atomic":
        return X86AtomicSimpleCPU()
    cpu = X86O3CPU()
    if model == "stock":
        return cpu      # O3 at gem5's DEFAULTS: ROB 192, LQ/SQ 32, IQ 64
    if model == "stock+iq":
        cpu.instQueues = [IQUnit(numEntries=97)]   # ONLY the IQ raised
        return cpu

    # -- front end ----------------------------------------------------------
    # Raptor Cove's LEGACY decoder is 6-wide, but that is not the sustained
    # rate: the 4096-uop DSB feeds the back end 8 uops/cycle, and allocation is
    # 8-wide. gem5 models no uop cache, so setting decode to 6 here would make
    # the front end the bottleneck in a way the real core never is -- it was,
    # and it cost ~2x on a front-end-bound loop. Model the SUSTAINED width.
    cpu.fetchWidth = 8
    cpu.fetchBufferSize = 64  # gem5 default; 32 HALVED fetch bandwidth
    cpu.fetchQueueSize = 64
    cpu.decodeWidth = 8
    cpu.renameWidth = 8  # Golden Cove allocates 8/cycle
    cpu.dispatchWidth = 8
    cpu.issueWidth = 12  # 12 execution ports
    cpu.wbWidth = 12
    cpu.commitWidth = 8  # 8-wide retire

    # -- out-of-order window ------------------------------------------------
    cpu.numROBEntries = 512
    cpu.instQueues = [IQUnit(numEntries=97)]  # unified reservation station
    cpu.LQEntries = 192
    cpu.SQEntries = 114
    cpu.numPhysIntRegs = 280
    cpu.numPhysFloatRegs = 332
    cpu.numPhysVecRegs = 332

    # -- branch prediction --------------------------------------------------
    # The real part uses an undisclosed TAGE-class predictor with a 12 K-entry
    # BTB. TAGE-SC-L 64 KB is gem5's nearest published equivalent -- it is a
    # CONDITIONAL predictor, which plugs into the BTB/RAS unit around it.
    cpu.branchPred = BranchPredictor()
    cpu.branchPred.conditionalBranchPred = TAGE_SC_L_64KB()
    # 12288 entries is the published Golden Cove BTB size. gem5 indexes the BTB
    # like a cache, so entries/associativity must be a power of two: 12288 = 3 x
    # 4096 admits 3-, 6- or 12-way. Intel does not publish the organisation; 6-way
    # (2048 sets) is the closest plausible shape that satisfies the constraint.
    cpu.branchPred.btb = SimpleBTB(numEntries=12288, associativity=6)
    cpu.branchPred.ras = ReturnAddrStack(numEntries=32)

    return cpu


def build(binary, args, model="o3", caches=True):
    system = System()
    system.clk_domain = SrcClockDomain(
        clock=CLOCK, voltage_domain=VoltageDomain()
    )
    system.mem_mode = "timing"
    system.mem_ranges = [AddrRange("2GiB")]  # matches one DDR5 device's capacity
    system.cache_line_size = LINE

    system.cpu = raptor_cove_core(model)

    system.membus = SystemXBar()
    if not caches:
        # gem5's own se.py default: NO cache hierarchy at all. Every access goes
        # straight to DRAM at a flat cost, so a split access costs exactly twice
        # -- and a smaller footprint buys nothing, because nothing is cached.
        system.cpu.icache_port = system.membus.cpu_side_ports
        system.cpu.dcache_port = system.membus.cpu_side_ports
        system.cpu.mmu.connectWalkerPorts(
            system.membus.cpu_side_ports, system.membus.cpu_side_ports)
        system.cpu.createInterruptController()
        system.cpu.interrupts[0].pio = system.membus.mem_side_ports
        system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
        system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports
        _finish(system)
        return _workload(system, binary, args)

    # -- private L1s, private L2, then the L3 -------------------------------
    system.cpu.icache = L1I()
    system.cpu.dcache = L1D()
    system.cpu.icache.cpu_side = system.cpu.icache_port
    system.cpu.dcache.cpu_side = system.cpu.dcache_port

    system.l2bus = L2XBar()
    system.cpu.icache.mem_side = system.l2bus.cpu_side_ports
    system.cpu.dcache.mem_side = system.l2bus.cpu_side_ports

    system.l2 = L2()
    system.l2.cpu_side = system.l2bus.mem_side_ports

    system.l3bus = L2XBar()
    system.l2.mem_side = system.l3bus.cpu_side_ports
    system.l3 = L3()
    system.l3.cpu_side = system.l3bus.mem_side_ports

    system.l3.mem_side = system.membus.cpu_side_ports

    # x86 needs the TLB walkers on the bus, and an interrupt controller.
    system.cpu.createInterruptController()
    system.cpu.interrupts[0].pio = system.membus.mem_side_ports
    system.cpu.interrupts[0].int_requestor = system.membus.cpu_side_ports
    system.cpu.interrupts[0].int_responder = system.membus.mem_side_ports
    system.cpu.mmu.connectWalkerPorts(
        system.l2bus.cpu_side_ports, system.l2bus.cpu_side_ports
    )

    _finish(system)
    return _workload(system, binary, args)


def _finish(system):
    # -- DRAM: the part pairs with DDR5-5600 --------------------------------
    system.mem_ctrl = MemCtrl()
    system.mem_ctrl.dram = DDR5_4400_4x8(range=system.mem_ranges[0])
    system.mem_ctrl.dram.tCK = "0.357ns"  # 5600 MT/s
    system.mem_ctrl.port = system.membus.mem_side_ports
    system.system_port = system.membus.cpu_side_ports



def _workload(system, binary, args):
    # -- the workload: syscall emulation ------------------------------------
    process = Process()
    process.cmd = [binary] + args
    system.workload = SEWorkload.init_compatible(binary)
    system.cpu.workload = process
    system.cpu.createThreads()
    return system


if __name__ == "__m5_main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmd", required=True, help="static binary to run")
    ap.add_argument("--args", default="", help="space-separated arguments")
    ap.add_argument("--cpu", default="o3", choices=["o3", "stock", "stock+iq", "timing", "atomic"],
                    help="CPU model (default o3 = the Raptor Cove core)")
    ap.add_argument("--no-caches", action="store_true",
                    help="omit the cache hierarchy (what gem5's se.py does by default)")
    opts = ap.parse_args()

    root = Root(full_system=False, system=build(opts.cmd, opts.args.split(), opts.cpu, not opts.no_caches))
    m5.instantiate()
    print(f"** running {opts.cmd} on one Raptor Cove P-core @ {CLOCK}")
    event = m5.simulate()
    print(f"** exiting @ tick {m5.curTick()} because {event.getCause()}")
