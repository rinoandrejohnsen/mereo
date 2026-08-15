#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // argc, not foldable
      if (n == 1) { Mark cold{101};
                    goto fault; }       // ~cold then ~keep
      { Mark hot{102}; }
    fault: ;
    }
    sysexit(1);
}
