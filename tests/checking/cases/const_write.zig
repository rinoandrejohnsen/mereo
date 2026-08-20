const msg: [2]u8 = .{ 'h', 'i' };
pub fn main() void {
    msg[0] = 'A';                               // MISTAKE
}
