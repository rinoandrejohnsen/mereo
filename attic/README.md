# attic

Nothing here is built, tested, or referenced by the toolchain. It is kept
because this project has no version control: everything that stopped being
current was moved here rather than deleted.

| | |
| --- | --- |
| `artifacts/` | stale build output — binaries, `mereoc` C that `build/` now holds, `.dis`/`.s` dumps |
| `experiments/` | hand-written C and C++ probes behind design decisions: `proposal_*.c` (dispatch shapes), `fsm*.c` (state machines), `branch_hand.c` / `branch_c.c` (the crossroad layout), `bench_spill.c` (register pressure) |
| `prototypes/` | the C++ ancestors of mereo — `error_handling/`, `linux/`, the `.h++` headers — plus early syntax mockups |
| `gem5/` | a Raptor Cove P-core model and its benchmarks. Its README records what the simulator got right (instruction counts, 1.8%) and wrong (cycle counts, alignment). It has not run since its Python 3.11 went away with `/tmp` |

If something here is wanted again, it moves back out — that is the point of
keeping it.

## migrations/

One-shot scripts that rewrote the whole corpus, kept so the change can be
audited and reproduced rather than taken on trust.

- `to_new_syntax.py` — the old surface (`write t where` + indented bindings,
  `count of arguments`, `use "..."`, `exit system`, no `end`) to the new one
  (`t.write (...)`, `arguments.count`, `include`, `linux:exit`, `end`).
  Deterministic: re-running it on a clean checkout of the commit before the
  switch reproduces the converted tree exactly, which is how one hand-edit that
  had crept in was found.
