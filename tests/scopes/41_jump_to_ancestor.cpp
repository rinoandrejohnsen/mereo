#include "parity.h++"
// this is scope_example.txt verbatim, with the scopes given something to hold:
// `goto parent_end` from the innermost block runs ~g, ~c, ~p on the way out.
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
    parent_start:
      { Mark p{101};
        { Mark c{102};
          { Mark g{103};
            if (n == 1) goto parent_end;   // OK: jumps outward
          }
        }
      }
    parent_end: ;
    }
    sysexit(0);
}
