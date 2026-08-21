#!/usr/bin/env python3
"""Interleaved A/B timing: alternate the two programs so drift hits both."""
import subprocess, sys, time, statistics as st
a, b, f, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
data = open(f, "rb").read()
ta, tb = [], []
for _ in range(3):                                     # warm
    for p in (a, b): subprocess.run([p], input=data, stdout=subprocess.DEVNULL)
for _ in range(n):
    for p, acc in ((a, ta), (b, tb)):
        t0 = time.perf_counter()
        subprocess.run([p], input=data, stdout=subprocess.DEVNULL)
        acc.append((time.perf_counter() - t0) * 1000)
for name, acc in ((a, ta), (b, tb)):
    print(f"  {name:<22} min {min(acc):6.1f}  median {st.median(acc):6.1f}  "
          f"mean {st.mean(acc):6.1f}  sd {st.pstdev(acc):5.2f}")
print(f"  median ratio {st.median(tb)/st.median(ta):.3f}  min ratio {min(tb)/min(ta):.3f}")
