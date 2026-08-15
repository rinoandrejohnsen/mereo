#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      { Mark o{103};
        { Mark h{101}; }               // fault-order: ~h, ~o, ~keep
      }
    }
    sysexit(1);
}
