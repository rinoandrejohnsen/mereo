#!/usr/bin/env bash
# Suite 2 -- BLACK-BOX tests of the shipped binaries. Each program is an opaque
# box: given stdin/args, assert its stdout and exit code. No knowledge of the
# internals (that is what scopes/ unit-tests). Part B re-runs the resource
# programs under mereoraii to assert -- on the real binary -- that fds are
# cleaned up and error records are correct on every fault path.
#
#   ./tests/blackbox.sh
set -u
DIR=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)
B=${OUT:-/tmp/mbuild/bb}; mkdir -p "$B"
# the shipped build, flag for flag -- this suite tests the binaries as they
# leave build.sh, layout included (see mereo.lds)
CFLAGS="-O2 -nostdlib -static -fno-stack-protector -fno-tree-loop-distribute-patterns -fwhole-program -fno-strict-aliasing -fno-asynchronous-unwind-tables -fno-ident"
CFLAGS="$CFLAGS -Wl,-T,$DIR/mereo.lds -Wl,-z,noseparate-code -Wl,--build-id=none -s"
printf 'lorem ipsum\n' > "$B/doc"

build() {
    local src="$DIR/examples/$1.mereo"
    [ -f "$src" ] || src="$DIR/tests/progs/$1.mereo"   # test-only programs
    # Reuse a binary only if it is newer than everything that shapes it. A
    # cached binary older than the compiler silently turns a real failure into
    # a pass -- which it once did, so the check is not hypothetical. core.mereo
    # was missing from this list until a deliberately broken `span.skip` was
    # reported as passing: BOTH libraries shape the binary, not just linux.
    if [ -x "$B/$1" ] && [ "$B/$1" -nt "$src" ] \
       && [ "$B/$1" -nt "$DIR/mereoc.py" ] && [ "$B/$1" -nt "$DIR/linux.mereo" ] \
       && [ "$B/$1" -nt "$DIR/core.mereo" ]; then
        return 0
    fi
    python3 "$DIR/mereoc.py" "$src" > "$B/$1.c" 2>/dev/null \
        && gcc $CFLAGS -o "$B/$1" "$B/$1.c" 2>/dev/null
}

pass=0 fail=0
# bb LABEL PROG STDIN EXIT EXPECT -- ARGS...   (trailing newlines ignored)
bb() {
    local label=$1 prog=$2 stdin=$3 want_exit=$4 want=$5; shift 5
    [ "${1:-}" = "--" ] && shift
    build "$prog" || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    local out rc
    out=$(cd "$DIR" && printf '%s' "$stdin" | timeout 10 "$B/$prog" "$@" 2>/dev/null); rc=$?
    if [ "$out" = "$want" ] && [ "$rc" = "$want_exit" ]; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s FAIL  exit %s/%s  out %q want %q\n' \
               "$label" "$rc" "$want_exit" "$out" "$want"; fail=$((fail+1))
    fi
}

echo "== A. behavior (stdin/args -> stdout, exit) =="
bb upper           upper    $'hello WORLD\n'  0  "HELLO WORLD"
bb span            span     $'host=localhost\nport=8080\n'  0 \
                                       $'host -> localhost\nport -> 8080'
# the two behaviours the example gets from CLAMPING rather than from a special
# case: a last line with no newline still comes out, and a line with no `=` is a
# key whose value is empty. Both would need an explicit branch if `skip` were
# C++'s `remove_prefix`, which makes n > size() undefined instead of clamping.
bb span/no-final-nl span    $'a=1\nb=2'       0  $'a -> 1\nb -> 2'
bb span/no-equals   span    $'bare\nk=v\n'    0  $'bare -> \nk -> v'
bb span/empty       span    ""               0  ""
bb branch/many     branch   "xyz"             0  "many bytes"
bb branch/nothing  branch   ""                0  "nothing"
bb branch/one      branch   "x"               0  "one byte"
bb basename/deep   basename ""               0  "c"      -- /a/b/c
bb basename/trail  basename ""               0  "lib"    -- /usr/lib/
# the rest of what the header claims, which was never pinned: the root, a bare
# name, an empty operand, a run of slashes, one trailing slash, and the
# missing-operand `ensure`. Written down before the walk was rewritten in terms
# of spans, so the rewrite had a full oracle rather than two cases of one.
bb basename/root   basename ""               0  "/"      -- /
bb basename/bare   basename ""               0  "foo"    -- foo
bb basename/empty  basename ""               0  ""       -- ""
bb basename/slashes basename ""              0  "/"      -- ///
bb basename/one-trail basename ""            0  "a"      -- a/
bb basename/gcc    basename ""               0  "gcc"    -- /usr/bin/gcc
bb basename/no-operand basename ""           1  ""
bb whoami          whoami   ""                0  "$(id -un)"
bb abc/loremfile   abc      ""                0  "$(cat "$DIR/lorem_ipsum.txt")"
bb argcat/file     argcat   ""                0  "lorem ipsum"  -- "$B/doc"
bb bits/exit       bits     "AB"              8  ""
# the byte handed to the kernel must be the one stored BEFORE the syscall: this
# prints "\x00" instead of "A" the moment a syscall's memory clobber is too
# narrow and GCC kills that store as dead (see mereoclobber.py)
bb clobber/order   clobber_order ""  0  "A"
# the json reader is an object view whose state is a block -- it went unchecked
# once, and a dropped field store turned into a null deref that no test saw
bb json/demo       jsondemo ""                0  $'mereo\n443'
bb json/test       jsontest ""                0  $'hello world\n8080\n-12'

# copy reads a fixed lorem_ipsum.txt and writes copy_out.txt (run in the repo)
build copy && (cd "$DIR" && rm -f copy_out.txt && "$B/copy") 2>/dev/null \
    && cmp -s "$DIR/lorem_ipsum.txt" "$DIR/copy_out.txt" \
    && { echo "  copy/roundtrip           ok"; pass=$((pass+1)); } \
    || { echo "  copy/roundtrip           FAIL"; fail=$((fail+1)); }
rm -f "$DIR/copy_out.txt"

echo
echo "== D. an object view: a layout carrying templates (the four shapes) =="
bb view/lensed        view_lens    "" 0 "G"   # tag 7 written and read back
bb view/given         view_given   "" 0 "E"   # tag 5 handed in
bb view/at-offset     view_offset  "" 0 "F"   # tag 6, at +4 not 0
bb view/bare          view_bare    "" 0 "@"   # owns a zeroed block
bb view/writes-field  view_write   "" 0 "E"   # a template WRITES its own fields
# ...and all three ways of writing a field must agree on its BYTE ORDER. The
# construction form used to store the value raw and read back byte-reversed.
bb view/byte-order    view_byteorder "" 0 "18 18 4660"
bb view/flag-template view_flagtpl "" 0 "B"   # ... at bit grain: mask/shift RMW
bb word/in-register   word_register "" 0 "H"  # `N bytes in register`: every
                                              # slice agrees with `in stack`
bb view/over-register view_register "" 0 "A"  # a view (and a flag view) laid
                                              # over a register word with `as`
bb view/over-scalar   view_scalar   "" 0 "A"  # ... and over a scalar, which is
                                              # that same word, `as signed`
bb view/unsigned-8    field_unsigned "" 0 "U" # an 8-byte field's reading is
                                              # honoured: `div`/`shr` vs
                                              # `idiv`/`sar` on the same bits

# THE THREE WAYS TO SAY THE SAME 24 BYTES:
#   long    a `N bytes` backing, then `data is backing as structure`
#   bare    `data is structure`            -- it owns the block, zero-filled
#   ctor    `data is structure where ...`  -- ... and fills it in one breath
# They describe identical memory, so they must compile to identical
# INSTRUCTIONS, not merely behave alike. `same` asserts that on .text, which
# caught the bare form's zero-fill being pinned above the rt_sigaction prologue
# and surviving to the binary at +14 bytes.
same() {  # same LABEL PROG...   -- every PROG's .text identical to the first
    local label=$1 first=$2 p; shift
    for p in "$@"; do
        build "$p" || { printf '  %-24s BUILD FAIL\n' "$label"
                        fail=$((fail+1)); return; }
        objcopy -O binary --only-section=.text "$B/$p" "$B/$p.text" 2>/dev/null
    done
    for p in "$@"; do
        cmp -s "$B/$first.text" "$B/$p.text" && continue
        printf '  %-24s CODE DIFFERS  %s=%s B vs %s=%s B\n' "$label" \
               "$first" "$(stat -c%s "$B/$first.text")" \
               "$p" "$(stat -c%s "$B/$p.text")"
        fail=$((fail+1)); return
    done
    printf '  %-24s ok\n' "$label"; pass=$((pass+1))
}
bb   view/form-long   layout_long "" 0 "AAAAAAAABBBBBBBBCCCCCCCC"
bb   view/form-bare   layout_bare "" 0 "AAAAAAAABBBBBBBBCCCCCCCC"
bb   view/form-ctor   layout_ctor "" 0 "AAAAAAAABBBBBBBBCCCCCCCC"
same view/same-code   layout_long layout_bare layout_ctor

# A TEMPLATE STANDING ALONE (top level, called by its own name) against the same
# template inside a group (called `TEMPLATE GROUP where`). A lone template is
# parsed into a group of one, so the two must not merely agree on output -- they
# must be the same binary.
bb   tmpl/alone       tmpl_alone $'hello WORLD\n' 0 "HELLO WORLD"
bb   tmpl/group       tmpl_group $'hello WORLD\n' 0 "HELLO WORLD"
same tmpl/same-code   tmpl_alone tmpl_group
# a template handing a LITERAL out through a port -- it read as a buffer
# declaration under the parameter's name and collided at the splice
bb   tmpl/literal-port tmpl_literal "" 0 "/hellohello world!"

# A TEMPLATE SPLICED INTO A BRANCH ROAD. The road planner used to know four step
# kinds; a template body brings stores, `ensure`s, loops and constructions, so a
# call in a road was rejected outright. Both roads here run one.
bb   tmpl/road-cold   tmpl_road ""  0  "CCCCC"
bb   tmpl/road-hot    tmpl_road ""  0  "HHH"     -- x
bb   tmpl/road-owns   tmpl_road_res "" 0 "$(cat "$DIR/lorem_ipsum.txt")"

# ---- the syscalls linux.mereo gained beyond its original 21. Each of these is
# checked against the GNU tool that makes the SAME call, so a wrong syscall
# number or a swapped register shows up as a wrong answer rather than as silence.

# ls: getdents64 paged over a directory big enough to need several calls, and
# the walk over d_reclen. Sorted here because mereo's answers in filesystem
# order and GNU's are sorted -- the SET of names is the claim.
lsdiff() {  # lsdiff LABEL DIR
    local label=$1 dir=$2
    build ls || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    if diff -q <(cd "$DIR" && timeout 10 "$B/ls" "$dir" | sort) \
                <(cd "$DIR" && command ls "$dir" | sort) >/dev/null; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s DIFFERS from GNU ls for %s\n' "$label" "$dir"; fail=$((fail+1))
    fi
}
lsdiff ls/small   docs
lsdiff ls/paged   /usr/bin

# stat: statx through the `file_status` layout view and the `file_mode` flag
# view, against GNU stat's own four fields. The paths cover every file KIND
# (regular, directory, symlink, char device) plus the sticky bit, which is what
# exercises `kind of` and the named bits.
statsame() {  # statsame LABEL PATH
    local label=$1 path=$2 mine theirs
    build stat || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    mine=$(cd "$DIR" && timeout 10 "$B/stat" "$path" | cut -d' ' -f1-4)
    theirs=$(stat -c '%A %h %u %s' "$path")
    if [ "$mine" = "$theirs" ]; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s mine=%q stat=%q\n' "$label" "$mine" "$theirs"; fail=$((fail+1))
    fi
}
statsame stat/regular  "$DIR/mereoc.py"
statsame stat/dir      "$DIR/docs"
statsame stat/chardev  /dev/null
# `cut -f1-4` above drops the FIFTH field -- the name -- so the operand echo was
# untested while the four numbers were pinned. It is the field the terminator
# scan produces, so it gets its own check: whole line, name included.
statname() {  # statname LABEL PATH EXPECTED-LINE
    local label=$1 path=$2 want=$3 mine
    build stat || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    mine=$(cd "$DIR" && timeout 10 "$B/stat" "$path")
    mine="$(stat -c '%A %h %u %s' "$path") $want"
    if [ "$(cd "$DIR" && timeout 10 "$B/stat" "$path")" = "$mine" ]; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s mine=%q want=%q\n' "$label" \
               "$(cd "$DIR" && timeout 10 "$B/stat" "$path")" "$mine"; fail=$((fail+1))
    fi
}
# `examples/getenv.mereo` walks envp with a RUNTIME index. `environment.pointer
# + i` took a literal until now, so there was no loop over the environment and
# no way to write this program at all. (The other half of that gap -- a layout
# view at a runtime address -- is exercised by `lsdiff` above: ls now reads
# getdents64 records through `[at : 19] as linux.dirent`.)
getenvsame() {  # getenvsame LABEL VAR
    local label=$1 var=$2 mine theirs
    build getenv || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    mine=$(cd "$DIR" && timeout 10 "$B/getenv" "$var"); theirs=$(printenv "$var")
    if [ "$mine" = "$theirs" ] && [ -n "$theirs" ]; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s mine=%q printenv=%q\n' "$label" "$mine" "$theirs"; fail=$((fail+1))
    fi
}
getenvsame getenv/path  PATH
getenvsame getenv/home  HOME
# unset exits non-zero and prints nothing; and a name that is a PREFIX of a real
# one must not match it, which is what comparing both lengths buys
bb   getenv/unset   getenv "" 1 ""  -- MEREO_NO_SUCH_VAR
bb   getenv/prefix  getenv "" 1 ""  -- PAT
bb   getenv/no-operand getenv "" 1 ""

statname stat/name-short /dev/null  /dev/null
statname stat/name-long  "$DIR/tests/blackbox.sh" "$DIR/tests/blackbox.sh"
statsame stat/sticky   /tmp

# ...and everything else linux.mereo declares, called once each. Every step
# there carries its primitive's `ensure`, so reaching the end is the assertion:
# mkdirat chdir openat statx getdents64 symlinkat readlinkat fchmodat
# faccessat2 renameat2 linkat unlinkat clock_gettime nanosleep pipe2 ppoll
# dup3 uname getuid getpid.
# the byte layer's second half: last (strrchr), upper/lower, the three ctype
# questions, and the hex pair. Every step in it carries an `ensure`, so a wrong
# answer fails the program rather than printing a wrong line.
bb   text/bytes       text_bytes "" 0 \
     "8 ABC abc 1 1 1 ff 2a00 deadbeef 48656c6c6f 3735928559"

# The two views, every method of each. `span` is C++'s string_view (find/rfind,
# contains, at, starts_with/ends_with, and the two MUTATORS remove_prefix and
# remove_suffix that stand in for the subrange factories mereo cannot express);
# `builder` is the append side, which the corpus had written out by hand 39
# times without ever checking that the bytes fit. The last line is the loop the
# pair exists for -- split on a byte with no offset arithmetic at the call site.
bb   views/all        views "" 0 \
'5 11 17 6 17
104 111
101010
world hello
world
0
hello hello 0 hello
abc 3 11
-4096 beef ...
[alpha][beta][gamma]'
# ...and the two `ensure`s that a raw pointer-and-count pair had nowhere to put:
# reading past the end of a span, and appending past the end of a builder. Both
# must END the program, not answer wrongly.
bb   views/at-past-end   views_at_past_end   "" 1 ""
bb   views/add-past-end  views_add_past_end  "" 1 ""
# `already` must STORE what it is handed, with or without a method on the
# definition. Without one, a layout used to take every value in silence and read
# back zero; a flag view emitted a store to an undeclared name and would not
# compile. Both shapes, both ways, one line.
bb   adopt/plain-values   adopt_plain "" 0  "1000 70000 1000 71000 1 2 1"

# `repeat program` goes back to the first step, past the entry views and the
# signal setup. The output pins the three passes; `raii/` below pins the half
# that matters more -- that each pass RELEASES what it took, inline, rather
# than leaking a descriptor per iteration.
bb   repeat/program  repeat_program "" 0 "LoremLoremLorem"

rm -rf /tmp/mereo_linux_calls
bb   linux/calls      linux_calls "" 0 "linux ok"
# ...and again, over the leftovers a crashed run would leave, which is what the
# four `or continue` repairs at the top are for
mkdir -p /tmp/mereo_linux_calls && : > /tmp/mereo_linux_calls/sample
bb   linux/calls-again linux_calls "" 0 "linux ok"

rejects() {  # rejects LABEL PROG SUBSTRING -- transpiling PROG must fail, saying SUBSTRING
    local label=$1 prog=$2 want=$3 msg
    msg=$(python3 "$DIR/mereoc.py" "$DIR/tests/progs/$prog.mereo" 2>&1 >/dev/null)
    if [ -n "$msg" ] && [ "${msg#*"$want"}" != "$msg" ]; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s FAIL  %q\n' "$label" "$msg"; fail=$((fail+1))
    fi
}
# A CROSSROAD NESTED IN A COLD ROAD: `number text` carries one (the leading `-`
# is a road), and this splices it into a `when` road. It was refused until the
# guarantee was read properly -- the nested dispatch sits where its enclosing
# road does, and its own roads go past it, still cold. Both are verified by
# mereocheck in the build gate; here we check it computes the right answer.
bb   tmpl/road-nest-cold tmpl_road_nest ""  0  "-42"
bb   tmpl/road-nest-hot  tmpl_road_nest ""  0  "7"    -- x

# A CONDITIONAL STORE -- `[ADDR : N] is VALUE when COND`, the one thing a value
# cascade cannot say (a cascade always ends in a write). And the `when` /
# `branchless` split: `when` states a dependence and lets the target lower it
# however it can; `branchless` REQUIRES no branch, and is refused where no
# machine mereo emits for could honour it.
bb   store/when-cold  store_when ""  0  "A.C"
bb   store/when-hot   store_when ""  0  "AB."   -- x
rejects store/no-branchless  store_branchless  "has a conditional store"
rejects when/no-speculation  when_speculative  "computes both arms"
rejects when/no-trap-divide  when_divide       "may be zero"

# `leave NAME` -- out of a loop from the middle, releasing what the iteration
# holds. It can only name a loop it sits inside, which is what keeps those
# releases derivable; a template may only leave a loop it opens itself.
bb   leave/early      loop_leave "abxde"  0  "2"
bb   leave/none       loop_leave "abcde"  0  "5"
bb   leave/first      loop_leave "xyz"    0  "0"
bb   leave/owns       loop_leave_res ""   0  "L"
bb   loop/nested-owns loop_nest_res ""   0  "LLLL"
# both roads of a crossroad owning a real descriptor -- which road ran is
# visible in the byte it prints. Those bytes are the FIRST BYTE of the file
# each road opens: `L` of lorem_ipsum.txt, `-` of linux.mereo's opening
# comment. The second changed from `#` when comments became `--`.
bb   branch/road-cold branch_res ""   0  "L"
bb   branch/road-hot  branch_res ""   0  "-"   -- x
rejects leave/alien-loop  loop_leave_alien  "neither itself nor one of its own"
# a ROAD is a scope too, so `leave LABEL` is its own break: release what the
# road took and rejoin the merge without running the rest of the arm. The step
# after each leave would clear the count, so the printed byte is the proof.
bb   branch/leave-cold branch_leave ""  0  "L"
bb   branch/leave-hot  branch_leave ""  0  "-"   -- x
# ... but a road has no START -- it is entered by the dispatch
rejects branch/no-repeat  branch_repeat  "a road has no start to go back to"

# `acquired when` marks where ownership BEGINS in a multi-call acquire -- the
# test before which a fault releases nothing and after which it releases the one
# thing. Its four refusals, none of which had a test:
rejects acquired/missing    acquired_missing    "which one takes ownership"
rejects acquired/twice      acquired_twice      "already marks an acquisition"
rejects acquired/in-release acquired_in_release "belongs in \`acquire\`"
rejects acquired/no-call    acquired_no_call    "must follow the call"

# A NAME BECOMES A C IDENTIFIER as written, and a scope name becomes a C LABEL.
# All three of these used to pass mereo and fail in GCC, with a message about
# generated code the author never saw.
rejects name/c-keyword  name_ckeyword   "is a C keyword"
rejects name/label      name_label      "collides with a label the emitter makes"
rejects name/underscore name_underscore "may not start with an underscore"

# Two more coreutils clones, checked against the GNU originals: `wc -l` (a
# refill loop with a branchless, vectorising count) and `head -n` (the same
# shape, stopped early by `leave`).
bb   coreutils/wcl      wcl  $'a\nb\nc\n'  0  "3"
bb   coreutils/wcl-partial wcl $'a\nb\nc'  0  "2"   # no trailing newline: 2
bb   coreutils/wcl-empty wcl  ""           0  "0"
bb   coreutils/head1    head $'a\nb\nc\n'  0  "a"          -- 1
bb   coreutils/head0    head $'a\nb\nc\n'  0  ""           -- 0
bb   coreutils/head-all head $'a\nb\nc\n'  0  $'a\nb\nc'  -- 9

# `GUARD goes` -- a conditional scope, mereo's `if`. An anonymous scope with an
# entry test, so it nests wherever a scope nests: this one is inside a loop,
# inside another guarded scope, inside a template, and inside a crossroad road.
bb   scope/guarded-hot  guarded_scope ""  0  "7"
bb   scope/guarded-cold guarded_scope ""  0  "1"   -- x
# the two things it must NOT be mistaken for
rejects cond/no-words     cond_word       "is\` is not a condition operator"
rejects cond/no-when-goes cond_when_goes  "a conditional scope is \`GUARD goes\`"

# `X.size` where an ADOPTED instance is built -- a resource's state (folded
# and top-declared) and an object view's (stored at the adopt step). It was the
# one place a compile-time size was refused, so programs counted their own
# literals by hand.
bb   adopt/size-of    adopt_sizeof "" 0 "hello world"

# MULTIPLE `repeat`: every one starts the named loop's next pass, so a non-final
# one skips the rest of it. The last is still what closes the loop -- and because
# it names its loop, `repeat OUTER` from an inner one is a multi-level continue.
bb   repeat/plain      loop_repeat "abcde"  0  "5"
bb   repeat/skips      loop_repeat "axbxc"  0  "3"
bb   repeat/with-leave loop_repeat "abzcd"  0  "2"
bb   repeat/all-skip   loop_repeat "xxxxx"  0  "0"
# `NAME goes` is a scope; a loop is one whose body ends by repeating. So a
# scope that never repeats is a named block, and a `leave` at the TOP with a
# `repeat` at the bottom is a while-loop -- zero passes, which a do-while
# could not say.
bb   scope/named-leave  scope_named ""  0  "="
bb   scope/named-through scope_named "" 0  "G"   -- x
# a TEMPLATE is a scope too: `leave` is an early return, `repeat` is a tail call
bb   scope/template   tmpl_scope ""  0  "A5"
# `leave program`: release everything and exit 0 from the middle -- it enters
# the tower rather than emitting a second copy of it
bb   scope/leave-prog  leave_program ""  0  ""
bb   scope/leave-prog2 leave_program ""  0  "L"   -- x

# `leave program` is the SAME unwinding as a failing `ensure` -- it enters the
# same tower at the same floor. Only the status and the record differ, so the
# close sequences must match exactly.
unwind_same() {   # unwind_same LABEL PROG   -- bare run vs `x` run
    local label=$1 prog=$2 a b
    build "$prog" || { printf '  %-24s BUILD FAIL\n' "$label"; fail=$((fail+1)); return; }
    a=$(cd "$DIR" && strace -e trace=close "$B/$prog"   2>&1 >/dev/null \
        | grep -oE 'close\(10[0-9]\)' | tr '\n' ' ')
    b=$(cd "$DIR" && strace -e trace=close "$B/$prog" x 2>&1 >/dev/null \
        | grep -oE 'close\(10[0-9]\)' | tr '\n' ' ')
    if [ -n "$a" ] && [ "$a" = "$b" ]; then
        printf '  %-24s ok   [%s]\n' "$label" "${a% }"; pass=$((pass+1))
    else
        printf '  %-24s DIFFER  leave:[%s] ensure:[%s]\n' "$label" "${a% }" "${b% }"
        fail=$((fail+1))
    fi
}
unwind_same scope/leave-eq-ensure leave_vs_ensure

echo "== C. nested control flow (loops/branches composed) =="
bb loop-in-loop          nestloop    ""  0  "........."
bb branch-in-loop        branchloop  ""  0  "ZLL"
bb loop-in-branch        loopbranch  ""  0  "yyy"

echo
echo "== B. RAII/error on the real binaries (mereoraii) =="
raii() {  # raii LABEL PROG -- ARGS...   (optional stdin via env RIN)
    local label=$1 prog=$2; shift 2; [ "${1:-}" = "--" ] && shift
    build "$prog" >/dev/null 2>&1
    if (cd "$DIR" && python3 "$DIR/mereoraii.py" ${RIN:+--stdin "$RIN"} \
            -- "$B/$prog" "$@") >/dev/null 2>&1; then
        printf '  %-24s ok\n' "$label"; pass=$((pass+1))
    else
        printf '  %-24s RAII PROBLEM\n' "$label"; fail=$((fail+1))
    fi
}
# `repeat program` releases INLINE rather than through the tower, so its
# cleanup is a second copy of the release and has to be checked as such: three
# passes must be three opens and three closes, on every fault path too.
raii repeat/program-raii repeat_program
raii whoami/raii     whoami
raii copy/raii       copy
# a resource ACQUIRED by a template spliced into a cold road: released before
# the road rejoins, and by the tower on every fault inside it
raii tmpl/road-raii  tmpl_road_res
# a loop that owns a file and is left from the middle: closed on the back-edge,
# on the `leave`, and on a fault at either syscall inside
raii leave/raii      loop_leave_res
# NESTED loops each owning a descriptor: 14 fault points, every one of which
# must release this inner pass, then this outer pass, then whatever is above
raii loop/nested-raii loop_nest_res
# a ROAD-local resource: released before the road rejoins the merge, and by the
# tower on every fault inside the road. Both roads, since only one runs per run.
raii branch/cold-raii branch_res
raii branch/hot-raii  branch_res -- x
# the same, on the arm that LEAVES the road early: the release the leave does
# and the tower's floors have to agree about what is still held
raii branch/leave-cold-raii branch_leave
raii branch/leave-hot-raii  branch_leave -- x
raii argcat/raii     argcat -- "$B/doc"
RIN="hi" raii abc/raii  abc
rm -f "$DIR/copy_out.txt"

echo "---"
echo "black-box: $pass ok, $fail fail"
exit $((fail > 0))
