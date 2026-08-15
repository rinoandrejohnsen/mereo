#include "parity.h++"
extern "C" void _start() {
    { Mark keep{103};
      volatile int n = 1;   // not foldable, as in the mereo twin
      if (n == 5) { Mark cold{102}; }       // when road (not taken)
      else        { Mark hot{101}; }        // likely road -> hot released here
    }                                        // keep at exit
    sysexit(0);
}
