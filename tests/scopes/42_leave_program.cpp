#include "parity.h++"
// C++ has no "return from main, unwinding" from a nested scope except by
// falling out of every one -- a goto to the end of the outermost block does it.
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      { Mark a{101};
        { Mark b{102};
          if (n == 1) goto done;   // ~b, ~a, ~keep on the way out
        }
      }
    done: ;
    }
    sysexit(0);
}
