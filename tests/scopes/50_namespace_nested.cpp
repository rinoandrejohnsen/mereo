#include "parity.h++"

namespace outer {
    struct handle { long fd; ~handle() { sysclose(fd); } };
    namespace inner {
        struct handle { long fd; ~handle() { sysclose(108); } };
    }
}

extern "C" void _start() {
    { outer::handle        a{101};
      outer::inner::handle b{102};
    }                                   // ~b then ~a: close(108) close(101)
    sysexit(0);
}
