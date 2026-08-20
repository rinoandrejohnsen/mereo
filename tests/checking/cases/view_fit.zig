// The same lens. `@ptrCast` reinterprets an address and does not check the
// size, so Zig accepts this. Its VALUE cast does check -- `@bitCast` on the
// same pair reports "size mismatch: destination has 128 bits but source has
// 32" -- so the gap here is specific to the pointer form, which is the one
// that corresponds to `as`.
const Rec = extern struct { a: u64, b: u64 };
pub fn main() void {
    var block: [4]u8 align(8) = undefined;
    const h: *Rec = @ptrCast(&block);           // MISTAKE
    h.a = 1;
}
