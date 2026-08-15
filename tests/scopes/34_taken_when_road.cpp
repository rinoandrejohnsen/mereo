#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      if (n == 1) { Mark cold{102}; }   // the road that runs
      else        { Mark hot{101}; }
    }
    sysexit(0);
}
