// Legal Zig, for the same reason.
fn down(n: i64) void { down(n); }               // MISTAKE
pub fn main() void { down(0); }
