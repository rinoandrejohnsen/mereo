#include "parity.h++"

// Two namespaces, the same type name in each, with different destructors.
namespace alpha { struct handle { long fd; ~handle() { sysclose(fd); } }; }
namespace beta  { struct handle { long fd; ~handle() { sysclose(109); } }; }

extern "C" void _start() {
    { alpha::handle a{101};
      beta::handle  b{102};
    }                                   // ~b then ~a: close(109) close(101)
    sysexit(0);
}
