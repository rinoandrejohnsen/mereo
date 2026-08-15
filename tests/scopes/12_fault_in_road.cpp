#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      { Mark hot{101};
      }                              // fault-order in the taken road: ~hot then ~keep
    }
    sysexit(1);
}
