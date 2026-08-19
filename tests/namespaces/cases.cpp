// The C++ twin of cases.mereo. Both print the same nine numbers.
//
// Each number is chosen so a WRONG resolution gives a different one: the three
// `rec`s have different widths and byte orders, and the three templates add
// 1, 100 and 1000, so picking the wrong one cannot agree by luck.
#include <cstdint>
#include <cstdio>
#include <cstring>

// 1. a top-level name...
struct rec { uint8_t tag; };

namespace alpha {
    // 2. ...and a namespace member of the same name. Two things.
    struct rec { uint16_t tag; };            // stored big-endian by hand below

    void tally(long &value) { value += 1; }

    namespace beta {
        struct rec { uint32_t tag; };        // 3. nested, the name again

        void reach(long &value) { tally(value); }   // 5. outward, unqualified

        void inner(long &value) { value += 100; }
        void near_(long &value) { inner(value); }   // 6. innermost wins
    }
}

namespace alpha {                            // 7. reopening the same namespace
    void late(long &value) { value += 1000; }
}

namespace delta {
    struct rec { uint8_t tag; };             // 8. a sibling namespace
}

void inner(long &value) { value += 1; }      // shadowed inside beta

int main() {
    unsigned char a[8] = {}, b[8] = {}, c[8] = {}, d[8] = {};

    auto *top  = reinterpret_cast<::rec *>(a);
    auto *mid  = reinterpret_cast<alpha::rec *>(b);
    auto *deep = reinterpret_cast<alpha::beta::rec *>(c);
    auto *sib  = reinterpret_cast<delta::rec *>(d);

    top->tag = 7;
    // mereo's `2 bytes as big` is a byte order stated in the layout; C++ has no
    // such thing, so the swap is written out -- which is the point being made.
    uint16_t be = __builtin_bswap16(0x1234);
    std::memcpy(&mid->tag, &be, sizeof be);
    deep->tag = 0x11223344;
    sib->tag = 5;

    long n;
    printf("%u", top->tag);
    printf(" %u", b[0]);                     // 0x12 first, if `mid` is 2 bytes big
    printf(" %u", c[0]);                     // 0x44 first, if `deep` is 4 bytes little
    printf(" %u", sib->tag);

    n = 0; alpha::tally(n);        printf(" %ld", n);
    n = 0; alpha::beta::reach(n);  printf(" %ld", n);
    n = 0; alpha::beta::near_(n);  printf(" %ld", n);
    n = 0; inner(n);               printf(" %ld", n);
    n = 0; alpha::late(n);         printf(" %ld", n);
    printf("\n");
    return 0;
}
