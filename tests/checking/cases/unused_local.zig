// Zig refuses this outright, and is the strictest of the three here.
pub fn main() void {
    const n: i64 = 0;
    const spare: i64 = 7;                       // MISTAKE
    _ = n;
}
