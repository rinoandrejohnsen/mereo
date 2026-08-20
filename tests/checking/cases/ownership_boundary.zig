// The same two-step acquisition. Cleanup on the error path is `errdefer`,
// written by hand -- and omitted here, which is the mistake. Nothing reports
// it: the code compiles and loses a descriptor when the second step fails.
const linux = @import("std").os.linux;

fn holder(path: [*:0]const u8) !i32 {           // MISTAKE
    const fd: i32 = @intCast(linux.open(path, .{}, 0));
    if (fd < 0) return error.Open;
    // errdefer _ = linux.close(fd);   <- the line that is missing
    if (@as(isize, @bitCast(linux.lseek(fd, 0, 0))) < 0) return error.Seek;
    return fd;
}

pub fn main() !void {
    _ = try holder("/dev/null");
}
