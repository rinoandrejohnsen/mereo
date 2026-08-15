#include "parity.h++"
// `leave outer` is a labelled break out of the OUTER loop from inside the
// inner one -- C++ needs a goto for that, which is what mereo emits too.
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // not foldable, as in the mereo twin
      for (int i = 0; i < 3; ++i) {
        Mark o{103};
        for (int j = 0; j < 2; ++j) {
          Mark t{101};
          if (n == 1) goto done;   // ~t then ~o run on the way out
        }
      }
      done:;
    }                              // keep at exit
    sysexit(0);
}
