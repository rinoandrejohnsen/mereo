#include "parity.h++"
extern "C" void _start() {
    { Mark keep{104};
      int i = 0, j = 0, k = 0;
    a:
      { Mark x{101};
        j = 0;
      b:
        { Mark y{102};
          k = 0;
        c:
          { Mark z{103};
            ++k;
            if (k < 2) goto c;
          }
          ++j;
          if (j < 2) goto b;
        }
        ++i;
        if (i < 2) goto a;
      }
    }
    sysexit(0);
}
