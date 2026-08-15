// C++ ground truth: the object was never constructed (its acquisition threw),
// so its destructor never runs -- only the one acquired before it is destroyed.
#include "parity.h++"
extern "C" void _start() {
    { Mark keep{102}; }
    sysexit(1);
}
