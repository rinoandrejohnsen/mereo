#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      { Mark tmp{101};
      }                              // fault-order: ~tmp then ~keep
    }
    sysexit(1);
}
