// C++ ground truth: the object WAS acquired (its resource is held) and then a
// later step failed, so it is destroyed -- then the one acquired before it.
#include "parity.h++"
extern "C" void _start() {
    { Mark keep{102}, thing{101}; }
    sysexit(1);
}
