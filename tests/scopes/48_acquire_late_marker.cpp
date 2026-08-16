// C++ ground truth: the constructor threw before the object owned anything --
// the preparatory check failed, ahead of the acquisition itself -- so no
// destructor runs for it. Only the object acquired before it is destroyed.
#include "parity.h++"
extern "C" void _start() {
    { Mark keep{102}; }
    sysexit(1);
}
