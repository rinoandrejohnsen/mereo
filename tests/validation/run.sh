#!/usr/bin/env bash
# Suite 8 -- WHAT THE VALIDATION CAN AND CANNOT SEE.
#
# Every other suite asks whether mereo does the right thing. This one asks a
# narrower question: for a program whose safety is decidable by hand, does the
# analysis decide it, and does it decide it the right way round.
#
# Three tiers, because the answer is different at each and the difference is
# the interesting part:
#
#   s_  SMALL   `linux.mereo` only. Buffers, indices, loops, guards. No
#               template is spliced, so this is the interval reasoning alone.
#   m_  MEDIUM  `core.mereo` as well. Every access is inside a template that
#               was spliced in, with the bound stated at the call site.
#   l_  LARGE   syscalls, promises, resources and templates together -- the
#               shape a real program has.
#
# Each capability is written twice: once where it holds and once where it does
# not. A checker that says nothing passes half of this suite and fails the
# other half, which is the point -- silence is not a pass here.
#
# THREE VERDICTS. `proves` means compiles with nothing on stderr. `refuses`
# means it does not compile. `reports` means it compiles and says what it could
# not decide -- which is the honest answer for an index off the wire whose
# range is a width rather than a value.
#
#   ./tests/validation/run.sh            all of it
#   ./tests/validation/run.sh s_         one tier
set -u
DIR=$(cd "$(dirname "$0")/../.." && pwd)
P="$DIR/tests/validation/progs"
ONLY=${1:-}

# WHAT THE ANALYSIS CANNOT DO YET, each with the reason and each PRINTED on
# every run. A listed case that starts behaving fails the suite too: that is
# the whole point of writing them down rather than editing the expectation.
declare -A KNOWN=(
  # ALL FIVE ARE ONE THING: two counters whose SUM is bounded, used
  # separately. An interval carries a bound on a name; it cannot carry the
  # correlation between two, so subtracting one term uses the other's floor
  # and the relation is gone.
  #
  #   builder   `data + count + i`, with `count + length <= limit`,
  #             `limit <= data.size` and `i < length`. Needs `count + i` under
  #             `limit`, which is `i < length` combined with the first fact.
  #   search    `at + j` where `at = data + i`, `i <= length - needle_length`
  #             and `j < needle_length`. Needs `i + j < length`. Same shape.
  #
  # mereo already does MORE of this than the tools it was measured against:
  # `tighten` keeps a fact as `key + others <= rhs`, which gets `line[held]`
  # and `arena[used]` in loglyze -- and Frama-C's Eva proves neither, with
  # intervals or with octagons. What it cannot do is carry the relation into a
  # DERIVED index. That wants a relational domain and is a large piece of work;
  # nothing smaller has been found.
  [m_builder_ok]="builder writes at data + count: two counters, one bounded sum"
  [m_builder_number]="the same, writing a decimal"
  [l_builder_over_read]="the same, appending after a read"
  [m_search_ok]="search hands equals data + i, then reads j past it: same shape"
  [m_json_ok]="the same, reached through json.text"
)

pass=0 fail=0
declare -a FAILED=() GAPS=()

check() {   # check EXPECT NAME
    local want=$1 name=$2
    [ -n "$ONLY" ] && case "$name" in $ONLY*) ;; *) return ;; esac
    local err rc got
    err=$(timeout 120 python3 "$DIR/mereoc.py" "$P/$name.mereo" 2>&1 >/dev/null); rc=$?
    if [ $rc -ne 0 ];                       then got=refuses
    elif printf '%s' "$err" | grep -q 'not proved'; then got=reports
    elif [ -n "$err" ];                     then got=other
    else                                         got=proves
    fi
    local why=${KNOWN[$name]:-}
    if [ "$got" = "$want" ]; then
        if [ -n "$why" ]; then
            fail=$((fail+1))
            FAILED+=("$(printf '  %-26s NOW %-8s -- drop it from KNOWN' "$name" "$got")")
        else
            pass=$((pass+1))
        fi
    elif [ -n "$why" ]; then
        pass=$((pass+1))
        GAPS+=("$(printf '  %-26s %-8s (want %-8s) %s' "$name" "$got" "$want" "$why")")
    else
        fail=$((fail+1))
        FAILED+=("$(printf '  %-26s want %-8s got %-8s %s' \
            "$name" "$want" "$got" "$(printf '%s' "$err" | head -1 | cut -c1-72)")")
    fi
}

# ---------------------------------------------------------------- small
check proves  s_const_in            # a constant index inside the buffer
check refuses s_const_out           # ...and one past it
check proves  s_loop_ceiling        # a counter the loop bounds above
check refuses s_loop_ceiling_out    # ...bounded past the buffer
check proves  s_loop_floor          # a DESCENDING counter, bounded below
check refuses s_loop_floor_out      # ...starting past the end
check proves  s_leave_fact          # `leave` states a bound; it holds after
check refuses s_leave_loose         # ...a bound too loose for what it indexes
check proves  s_equality            # `k == 4` bounds k from both sides
check refuses s_equality_out        # ...at a value that puts the load past
check proves  s_affine              # i * 4 under a ceiling on i
check refuses s_affine_out          # ...one step too many
check proves  s_width_exact         # an 8-byte load ending on the last byte
check refuses s_width_over          # ...one byte further on
check proves  s_mask                # `& 15` bounds whatever is behind it
check refuses s_mask_out            # ...a mask wider than the buffer
check proves  s_mask_carried        # ...and the same mask round a loop
check refuses s_cond_scope_kill     # a definition in a scope that CLOSED does
                                    # not kill what came before it
check refuses s_backedge_nested     # ...nor over a back edge: unconditional 40,
check proves  s_backedge_nested_ok  # nested 4, so both reach the head
check proves  s_modulo              # `% 16`
check proves  s_shift               # `>> 4` on a byte
check reports s_carried_outer       # a value grown in an OUTER loop, read in an
                                    # inner one: nothing bounds it, and it was
                                    # being PROVED from its declared value
check proves  s_carried_outer_ok    # ...reset each pass, so it is inside
check proves  s_nested_bound        # bounds from two enclosing scopes
check proves  s_when_store          # a conditional store, bounded either way
check refuses s_when_store_out      # ...where one branch is past the end
check reports s_field_store_stale   # a field store mutates its instance, so
                                    # the adopted value stops being believed
check proves  s_size_of             # the buffer states its own size
check proves  s_port_store          # a template that only STORES, in range
check refuses s_port_store_over     # ...past the end. Nothing is READ here.
check refuses s_port_load_over      # the same template READING, for contrast
check proves  s_dead_after_leave     # a `leave` whose condition FOLDS to true
                                    # puts the rest of its scope out of reach,
                                    # and an access that cannot happen is not
                                    # something to ask a bound for
check refuses s_dead_leave_false    # ...folds to FALSE, so the body does run
check refuses s_dead_leave_nested   # ...nested, so it may never be reached
check proves  s_subtract            # `k - 8` under a guard that keeps k >= 8
check reports s_subtract_under      # ...with nothing keeping it there

# --------------------------------------------------------------- medium
check proves  m_copy_bounded        # copy a length both sides can take
check refuses m_copy_over           # ...longer than the source has
check proves  m_fill_bounded        # fill inside the target
check refuses m_fill_over           # ...past it
check proves  m_format              # twenty bytes, which is what itoa needs
check refuses m_format_small        # ...four, which is not
check proves  m_find_promise        # the offset checked before it is used
check refuses m_find_at_end         # ...used unchecked, and "absent" is length
check refuses m_find_other_buffer   # ...bounded by one buffer, indexing another
check proves  m_measure             # measure answers no more than its limit
check proves  m_upper               # walks the length it is given
check refuses m_upper_over          # ...past the end of it
check proves  m_span_fit            # a view over bytes it fits inside
check refuses m_span_over           # ...claiming more than its backing has
check proves  m_span_skip           # `skip` narrows, and the rest is inside
check proves  m_starts_short        # a needle LONGER than the view: the short
check proves  m_ends_short          # case is ruled out before the compare, so
                                    # nothing outside the view is ever read
check proves  m_span_at             # one byte at an offset the view covers
check proves  m_span_at_over        # ...past it: `ensure offset < length`
                                    # catches that at run time, so nothing
                                    # unsafe is emitted. Refusing a statically
                                    # FALSE ensure would be better still.
check proves  m_builder_ok          # a builder filling its own backing
check refuses m_builder_over_limit  # ...a limit the backing cannot hold
check proves  m_builder_number      # a decimal number, which needs room
check proves  m_search_ok           # a needle with room, offset checked
check proves  m_json_ok             # a json reader over a constant document
check proves  m_number              # digits within the length given

# ---------------------------------------------------------------- large
check proves  l_read_bounded        # `count <= capacity` bounds the index
check refuses l_read_other_buffer   # ...bounded by the buffer it FILLED
check refuses l_read_capacity_over  # a capacity bigger than the buffer
check proves  l_write_bounded       # a write of what the buffer holds
check refuses l_write_over          # ...of more
check proves  l_wire_guarded        # a wire value, checked before use
check reports l_wire_unguarded      # ...unchecked: a width, not a value
check proves  l_span_over_read      # a view over what a read actually filled
check proves  l_builder_over_read   # a builder appending after a read
check proves  l_template_chain      # a promise carried through two splices
check refuses l_template_chain_over # ...ending at a smaller buffer
check proves  l_resource_access     # an owned resource, released on every path
check refuses l_resource_access_over
check proves  l_loop_over_read      # a loop walking what a read filled
check refuses l_loop_over_read_out  # ...eight at a time, without room for the last

if [ ${#GAPS[@]} -gt 0 ]; then
    echo "  -- recorded gaps, printed so they stay visible --"
    printf '%s\n' "${GAPS[@]}"
fi
if [ ${#FAILED[@]} -gt 0 ]; then
    printf '%s\n' "${FAILED[@]}"
fi
printf 'validation: %d ok, %d fail, %d recorded gaps\n' "$pass" "$fail" "${#GAPS[@]}"
[ "$fail" = 0 ]
