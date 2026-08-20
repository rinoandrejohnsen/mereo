// The same lens: a reinterpretation, not a conversion. C++ does not check that
// the destination fits the storage.
#include <cstdint>
struct Rec { uint64_t a, b; };
int main() {
    unsigned char block[4] = {};
    Rec *h = reinterpret_cast<Rec *>(block);    // MISTAKE
    h->a = 1;
    return static_cast<int>(h->a);
}
