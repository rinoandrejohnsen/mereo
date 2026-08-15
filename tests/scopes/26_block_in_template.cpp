// C++ ground truth: nested scopes destroy inner-first at each closing brace,
// and the object the caller made outlives the call. Splicing a template changes
// nothing about that -- 102, then 101, then 103.
#include "parity.h++"
extern "C" void _start() {
    { Mark c{103};
      { Mark a{101};
        { Mark b{102}; }
      }
    }
    sysexit(0);
}
