#include "parity.h++"

namespace one {
    struct handle { long fd; ~handle() { sysclose(fd); } };
    struct deep : handle { ~deep() { sysclose(107); } };
}
namespace two {
    struct handle { long fd; ~handle() { sysclose(108); } };
}

extern "C" void _start() {
    { one::handle a{101};
      two::handle b{102};
      one::deep   c{103};
    }                       // ~c (107 then 103), ~b (108), ~a (101)
    sysexit(1);
}
