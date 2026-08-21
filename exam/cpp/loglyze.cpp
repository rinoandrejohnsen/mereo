// loglyze -- summarise NCSA Common Log Format. See exam/SPEC.md.
//
// The third writing of the same program. The C twin is freestanding and
// hand-rolled to the byte; this one is the opposite brief: give C++ everything
// it has and see whether the abstractions and the standard library beat code
// written by hand.
//
// So it is HOSTED, and it uses the library wherever the library is plausibly
// better than a hand-rolled loop:
//
//   memchr        glibc dispatches to an AVX2 implementation, which scans 32
//                 bytes a step against the SWAR twin's 8
//   from_chars    the fastest integer parse in the standard, and it validates
//   to_chars      likewise for output, with no format string to interpret
//   string_view   the whole parse is subranges of one buffer, which is what a
//                 view is for -- and it costs nothing at run time
//   partial_sort  ten winners out of 8192 in one pass with a heap, against the
//                 C twin's ten linear passes over the whole table
//
// What it does NOT do is allocate. `std::unordered_map` would be the idiomatic
// choice for the path table and it is the wrong one here: the spec fixes the
// storage, and a node-per-key hash map would lose on both counts. The table is
// open-addressed by hand, as in the C -- which is itself a finding about where
// the standard library stops helping.
//
//   g++ -O2 -o loglyze_cpp exam/cpp/loglyze.cpp

#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <unistd.h>

namespace {

constexpr std::size_t LINE_MAX_   = 8192;
constexpr std::size_t PATH_MAX_   = 255;
constexpr std::size_t TABLE_BITS  = 13;
constexpr std::size_t TABLE_SLOTS = 1u << TABLE_BITS;
constexpr std::size_t TABLE_MAX   = 4096;
constexpr std::size_t ARENA_MAX   = 1u << 20;
constexpr std::size_t READ_BUF    = 64u << 10;
constexpr std::size_t TOP_N       = 10;

using u64 = std::uint64_t;
using u32 = std::uint32_t;

// ---------------------------------------------------------------- storage
alignas(64) std::array<char, LINE_MAX_> line{};
alignas(64) std::array<char, READ_BUF>  rbuf{};
alignas(64) std::array<char, ARENA_MAX> arena{};
u32 arena_used = 0;

struct Slot { u32 hash, off, len, count, seq; };
std::array<Slot, TABLE_SLOTS> slot{};
u32 live = 0;

u64 requests = 0, total_bytes = 0, malformed = 0;
std::array<u64, 5> klass{};

// A table beats five comparisons, and constexpr means it is built at compile
// time rather than being a static initialiser someone has to trust.
constexpr std::array<bool, 256> space_table = [] {
    std::array<bool, 256> t{};
    for (unsigned char c : {' ', '\t', '\r', '\v', '\f'}) t[c] = true;
    return t;
}();
inline bool is_space(char c) noexcept {
    return space_table[static_cast<unsigned char>(c)];
}

// ------------------------------------------------------------------ parse
// FNV-1a, the same as the C twin so the two agree slot for slot.
inline u32 hash_of(std::string_view s) noexcept {
    u32 h = 2166136261u;
    for (char c : s) { h ^= static_cast<unsigned char>(c); h *= 16777619u; }
    return h;
}

// memchr, not a loop. glibc picks an AVX2 implementation at load time, so this
// is the one place the standard library is expected to beat the hand-written C.
inline std::size_t find_byte(std::string_view s, char b) noexcept {
    const void *p = std::memchr(s.data(), static_cast<unsigned char>(b), s.size());
    return p ? static_cast<std::size_t>(static_cast<const char *>(p) - s.data())
             : s.size();
}

void intern(std::string_view p) noexcept {
    const u32 h = hash_of(p);
    const u32 n = static_cast<u32>(p.size());
    u32 i = h & (TABLE_SLOTS - 1);
    for (;;) {
        if (slot[i].count == 0) break;
        if (slot[i].hash == h && slot[i].len == n
            && std::string_view(arena.data() + slot[i].off, n) == p) {
            slot[i].count++;
            return;
        }
        i = (i + 1) & (TABLE_SLOTS - 1);
    }
    if (live >= TABLE_MAX || arena_used + n > ARENA_MAX) return;
    std::memcpy(arena.data() + arena_used, p.data(), n);
    slot[i] = Slot{h, arena_used, n, 1, live};
    arena_used += n;
    live++;
}

// one line, already truncated to LINE_MAX_ and with no newline in it
void do_line(std::string_view s) noexcept {
    const std::size_t n = s.size();

    const std::size_t q1 = find_byte(s, '"');
    if (q1 == n) { malformed++; return; }
    const std::size_t q2 = q1 + 1 + find_byte(s.substr(q1 + 1), '"');
    if (q2 >= n) { malformed++; return; }

    // inside the quotes: METHOD SP PATH [SP VERSION]
    const std::string_view req = s.substr(q1 + 1, q2 - q1 - 1);
    const std::size_t sp = find_byte(req, ' ');
    if (sp == req.size()) { malformed++; return; }
    const std::string_view rest = req.substr(sp + 1);
    const std::string_view path = rest.substr(0, find_byte(rest, ' '));
    if (path.empty() || path.size() > PATH_MAX_) { malformed++; return; }

    // after the quotes: STATUS BYTES
    std::size_t t = q2 + 1;
    while (t < n && is_space(s[t])) t++;
    const std::size_t st_s = t;
    while (t < n && !is_space(s[t])) t++;
    const std::string_view st = s.substr(st_s, t - st_s);
    while (t < n && is_space(s[t])) t++;
    const std::size_t by_s = t;
    while (t < n && !is_space(s[t])) t++;
    const std::string_view by = s.substr(by_s, t - by_s);

    if (st.empty() || by.empty()) { malformed++; return; }
    if (st.size() != 3) { malformed++; return; }
    for (char c : st) if (c < '0' || c > '9') { malformed++; return; }

    // from_chars validates and parses in one pass, and rejects a leading sign
    // or space -- which is exactly the spec's "a run of digits".
    u64 nb = 0;
    if (by.size() == 1 && by[0] == '-') {
        nb = 0;
    } else {
        const auto [ptr, ec] = std::from_chars(by.data(), by.data() + by.size(), nb);
        if (ec != std::errc{} || ptr != by.data() + by.size()) { malformed++; return; }
    }

    requests++;
    total_bytes += nb;
    const u32 c = static_cast<u32>(st[0] - '0');
    if (c >= 1 && c <= 5) klass[c - 1]++;
    intern(path);
}

// ----------------------------------------------------------------- output
std::array<char, 1 << 16> obuf{};
std::size_t olen = 0;

inline void emit(std::string_view s) noexcept {
    std::memcpy(obuf.data() + olen, s.data(), s.size());
    olen += s.size();
}
inline void emit_u64(u64 v) noexcept {
    const auto [ptr, ec] = std::to_chars(obuf.data() + olen,
                                         obuf.data() + obuf.size(), v);
    olen = static_cast<std::size_t>(ptr - obuf.data());
}

void report() noexcept {
    static constexpr std::string_view names[5] = {"1xx ", "2xx ", "3xx ", "4xx ", "5xx "};
    emit("requests ");  emit_u64(requests);    emit("\n");
    emit("bytes ");     emit_u64(total_bytes); emit("\n");
    emit("malformed "); emit_u64(malformed);   emit("\n");
    for (std::size_t i = 0; i < 5; i++) { emit(names[i]); emit_u64(klass[i]); emit("\n"); }
    emit("top\n");

    // The C twin takes ten linear passes over 8192 slots, marking what it has
    // taken. partial_sort does it in one pass with a heap of ten -- the clearest
    // place in the program where reaching for the library is simply better.
    std::array<const Slot *, TABLE_MAX> live_slots{};
    std::size_t k = 0;
    for (const Slot &s : slot) if (s.count) live_slots[k++] = &s;

    const std::size_t want = std::min(k, TOP_N);
    const auto better = [](const Slot *a, const Slot *b) noexcept {
        if (a->count != b->count) return a->count > b->count;
        return a->seq < b->seq;                       // ties: first seen wins
    };
    std::partial_sort(live_slots.begin(), live_slots.begin() + want,
                      live_slots.begin() + k, better);

    for (std::size_t i = 0; i < want; i++) {
        const Slot *s = live_slots[i];
        emit_u64(s->count);
        emit(" ");
        emit(std::string_view(arena.data() + s->off, s->len));
        emit("\n");
    }

    for (std::size_t done = 0; done < olen; ) {
        const ssize_t w = ::write(1, obuf.data() + done, olen - done);
        if (w <= 0) break;
        done += static_cast<std::size_t>(w);
    }
}

// ------------------------------------------------------------------- main
void run() noexcept {
    std::size_t held = 0;          // bytes of a straddling line held in `line`
    bool over = false;             // ...and whether that line already overflowed

    for (;;) {
        const ssize_t got = ::read(0, rbuf.data(), rbuf.size());
        if (got < 0) return;
        if (got == 0) {
            if (held) do_line(std::string_view(line.data(), held));
            return;
        }
        std::string_view in(rbuf.data(), static_cast<std::size_t>(got));

        while (!in.empty()) {
            const std::size_t j = find_byte(in, '\n');
            const std::string_view chunk = in.substr(0, j);
            const bool complete = (j < in.size());

            if (!held && !over && complete) {
                do_line(chunk.substr(0, std::min(chunk.size(), LINE_MAX_)));
            } else {
                if (!over) {
                    const std::size_t room = LINE_MAX_ - held;
                    const std::size_t take = std::min(chunk.size(), room);
                    std::memcpy(line.data() + held, chunk.data(), take);
                    held += take;
                    if (take < chunk.size()) over = true;
                }
                if (complete) {
                    do_line(std::string_view(line.data(), held));
                    held = 0;
                    over = false;
                }
            }
            in.remove_prefix(complete ? j + 1 : j);
        }
    }
}

}  // namespace

int main() {
    run();
    report();
    return 0;
}
