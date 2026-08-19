#include "parity.h++"

namespace lib {
    struct base { long fd; ~base() { sysclose(fd); } };
    // the added layer is destroyed before the base subobject
    struct deep : base { ~deep() { sysclose(107); } };
}

extern "C" void _start() {
    { lib::deep d{101}; }               // ~deep then ~base: close(107) close(101)
    sysexit(0);
}
