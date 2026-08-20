// Zig decides this one: the index and the length are both comptime-known.
pub fn main() void {
    var block: [8]u8 = undefined;
    block[100] = 1;                             // MISTAKE
}
