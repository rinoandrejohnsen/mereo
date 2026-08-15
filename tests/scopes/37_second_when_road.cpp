#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      volatile int n = 1;   // argc, not foldable
      if (n == 5)      { Mark x{102}; }
      else if (n == 1) { Mark y{103}; }   // the road that runs
      else             { Mark h{101}; }
    }
    sysexit(0);
}
