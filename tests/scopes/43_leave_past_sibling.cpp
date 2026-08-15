#include "parity.h++"
// `late` sits in its own block: C++ forbids a goto that jumps over a variable's
// initialisation in the same scope, but jumping over a whole block is fine --
// the same rule that makes mereo's ancestor-only jumps decidable.
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
      { Mark a{101}; }                  // the sibling closes here
      { Mark b{102};
        if (n == 1) goto done;          // ~b, then ~keep -- never ~a again
      }
      { Mark late{103}; }
    done: ;
    }
    sysexit(0);
}
