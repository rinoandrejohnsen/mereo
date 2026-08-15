#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      for (int i = 0; i < 2; ++i) { Mark o{103};
        for (int j = 0; j < 2; ++j) { Mark it{101}; }
      }
    }
    sysexit(0);
}
