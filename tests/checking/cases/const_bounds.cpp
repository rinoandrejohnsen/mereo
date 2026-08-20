// The same access. `std::array::operator[]` is unchecked by design; `.at()`
// checks at RUN time. Neither is a compile-time refusal.
#include <array>
int main() {
    std::array<char, 8> block{};
    return block[100];                          // MISTAKE
}
