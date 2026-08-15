#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      { Mark outer{102};
        { Mark inner{101}; }        // 101
      }                             // 102
    }                               // 103
    sysexit(0);
}
