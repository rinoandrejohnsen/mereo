#include "gcc-plugin.h"

#include "config.h"
#include "system.h"
#include "coretypes.h"
#include "tree.h"

#include "basic-block.h"
#include "c-family/c-common.h"
#include "cfghooks.h"
#include "context.h"
#include "diagnostic-core.h"
#include "function.h"
#include "gimple.h"
#include "gimple-expr.h"
#include "gimple-iterator.h"
#include "plugin-version.h"
#include "stringpool.h"
#include "tree-cfg.h"
#include "tree-iterator.h"
#include "tree-pass.h"
#include "attribs.h"

int plugin_is_GPL_compatible;

namespace {

constexpr const char *k_autocheck_attr = "eh_autocheck";
constexpr const char *k_autoreturn_attr = "eh_autoreturn";
constexpr const char *k_error_symbol = "eh_error";
constexpr const char *k_cleanup_label = "eh_cleanup";
constexpr const char *k_cleanup_marker = "eh_cleanup_marker";

static tree global_error_decl;

static tree
handle_function_attribute(const char *attr_name,
                          tree *node,
                          bool *no_add_attrs)
{
    tree decl = *node;

    if (TREE_CODE(decl) != FUNCTION_DECL) {
        warning(OPT_Wattributes, "%qE attribute only applies to functions",
                get_identifier(attr_name));
        *no_add_attrs = true;
    }

    return NULL_TREE;
}

static tree
handle_eh_autocheck_attribute(tree *node, tree, tree, int, bool *no_add_attrs)
{
    return handle_function_attribute(k_autocheck_attr, node, no_add_attrs);
}

static tree
handle_eh_autoreturn_attribute(tree *node, tree, tree, int, bool *no_add_attrs)
{
    return handle_function_attribute(k_autoreturn_attr, node, no_add_attrs);
}

static attribute_spec eh_autocheck_attr = {
    k_autocheck_attr,
    0,
    0,
    true,
    false,
    false,
    false,
    handle_eh_autocheck_attribute,
    nullptr,
};

static attribute_spec eh_autoreturn_attr = {
    k_autoreturn_attr,
    0,
    0,
    true,
    false,
    false,
    false,
    handle_eh_autoreturn_attribute,
    nullptr,
};

static bool
function_decl_has_attribute(tree fndecl, const char *attr_name)
{
    return fndecl
        && lookup_attribute(attr_name, DECL_ATTRIBUTES(fndecl)) != NULL_TREE;
}

static bool
function_has_autocheck_attribute()
{
    return function_decl_has_attribute(current_function_decl, k_autocheck_attr);
}

static tree
find_global_error_decl()
{
    tree id = get_identifier(k_error_symbol);
    tree decl = global_error_decl;

    if (decl == NULL_TREE) {
        decl = lookup_name(id);
    }

    if (decl == NULL_TREE || TREE_CODE(decl) != VAR_DECL) {
        error("EH plugin requires global register variable %qE", id);
        return NULL_TREE;
    }

    if (!POINTER_TYPE_P(TREE_TYPE(decl)) && !INTEGRAL_TYPE_P(TREE_TYPE(decl))) {
        error("%qE must have pointer or integer type", decl);
        return NULL_TREE;
    }

    return decl;
}

static location_t
tree_location_or_unknown(tree stmt)
{
    return stmt && EXPR_HAS_LOCATION(stmt) ? EXPR_LOCATION(stmt) : UNKNOWN_LOCATION;
}

static tree
build_error_autoreturn_check(tree error_decl, location_t loc)
{
    tree zero = build_zero_cst(TREE_TYPE(error_decl));
    tree cond = build2(NE_EXPR, boolean_type_node, error_decl, zero);
    tree ret = build1(RETURN_EXPR, void_type_node, NULL_TREE);
    tree empty = build_empty_stmt(loc);
    tree check = build3(COND_EXPR, void_type_node, cond, ret, empty);

    if (EXPR_P(cond)) {
        SET_EXPR_LOCATION(cond, loc);
    }
    if (EXPR_P(ret)) {
        SET_EXPR_LOCATION(ret, loc);
    }
    if (EXPR_P(check)) {
        SET_EXPR_LOCATION(check, loc);
    }

    return check;
}

static bool
tree_contains_runtime_call(tree node)
{
    if (node == NULL_TREE) {
        return false;
    }

    const enum tree_code code = TREE_CODE(node);

    if (code == CALL_EXPR || code == AGGR_INIT_EXPR) {
        return true;
    }

    if (code == STATEMENT_LIST) {
        for (tree_stmt_iterator it = tsi_start(node);
             !tsi_end_p(it);
             tsi_next(&it)) {
            if (tree_contains_runtime_call(tsi_stmt(it))) {
                return true;
            }
        }
        return false;
    }

    /*
     * A cleanup/finally expression is not a normal forward call site. Testing
     * r15 from inside cleanup code can turn destruction itself into control
     * flow, which is not what this experiment is trying to measure.
     */
    if (code == TRY_FINALLY_EXPR) {
        return tree_contains_runtime_call(TREE_OPERAND(node, 0));
    }
    if (code == CLEANUP_STMT) {
        return tree_contains_runtime_call(TREE_OPERAND(node, 0));
    }

    const enum tree_code_class code_class = TREE_CODE_CLASS(code);
    if (code_class == tcc_declaration
        || code_class == tcc_type
        || code_class == tcc_constant
        || code_class == tcc_exceptional) {
        return false;
    }

    const int length = TREE_OPERAND_LENGTH(node);
    for (int index = 0; index < length; ++index) {
        if (tree_contains_runtime_call(TREE_OPERAND(node, index))) {
            return true;
        }
    }

    return false;
}

static unsigned int
instrument_autoreturn_tree(tree node, tree error_decl);

static unsigned int
instrument_statement_list(tree statement_list, tree error_decl)
{
    unsigned int inserted = 0;

    for (tree_stmt_iterator it = tsi_start(statement_list);
         !tsi_end_p(it);
         tsi_next(&it)) {
        tree stmt = tsi_stmt(it);

        inserted += instrument_autoreturn_tree(stmt, error_decl);

        if (!tree_contains_runtime_call(stmt)) {
            continue;
        }

        tree check = build_error_autoreturn_check(error_decl,
                                                  tree_location_or_unknown(stmt));
        tsi_link_after(&it, check, TSI_SAME_STMT);
        ++inserted;
    }

    return inserted;
}

static unsigned int
instrument_autoreturn_tree(tree node, tree error_decl)
{
    if (node == NULL_TREE) {
        return 0;
    }

    switch (TREE_CODE(node)) {
    case STATEMENT_LIST:
        return instrument_statement_list(node, error_decl);

    case BIND_EXPR:
        return instrument_autoreturn_tree(BIND_EXPR_BODY(node), error_decl);

    case CLEANUP_POINT_EXPR:
        return instrument_autoreturn_tree(TREE_OPERAND(node, 0), error_decl);

    case TRY_FINALLY_EXPR:
        return instrument_autoreturn_tree(TREE_OPERAND(node, 0), error_decl);

    case TRY_CATCH_EXPR:
        return instrument_autoreturn_tree(TREE_OPERAND(node, 0), error_decl);

    case CLEANUP_STMT:
        return instrument_autoreturn_tree(TREE_OPERAND(node, 0), error_decl);

    case COND_EXPR:
        return instrument_autoreturn_tree(TREE_OPERAND(node, 1), error_decl)
            + instrument_autoreturn_tree(TREE_OPERAND(node, 2), error_decl);

    default:
        return 0;
    }
}

static tree
find_cleanup_label(basic_block *cleanup_bb)
{
    basic_block bb = nullptr;

    FOR_EACH_BB_FN(bb, cfun) {
        for (gimple_stmt_iterator gsi = gsi_start_bb(bb);
             !gsi_end_p(gsi);
             gsi_next(&gsi)) {
            gimple *stmt = gsi_stmt(gsi);

            if (!is_gimple_call(stmt)) {
                continue;
            }

            tree fndecl = gimple_call_fndecl(as_a<gcall *>(stmt));
            if (fndecl == NULL_TREE || DECL_NAME(fndecl) == NULL_TREE) {
                continue;
            }

            if (strcmp(IDENTIFIER_POINTER(DECL_NAME(fndecl)),
                       k_cleanup_marker) == 0) {
                *cleanup_bb = bb;
                return gimple_block_label(bb);
            }
        }
    }

    FOR_EACH_BB_FN(bb, cfun) {
        for (gimple_stmt_iterator gsi = gsi_start_bb(bb);
             !gsi_end_p(gsi);
             gsi_next(&gsi)) {
            gimple *stmt = gsi_stmt(gsi);

            if (gimple_code(stmt) != GIMPLE_LABEL) {
                continue;
            }

            tree label = gimple_label_label(as_a<glabel *>(stmt));
            tree name = DECL_NAME(label);

            if (name != NULL_TREE
                && strcmp(IDENTIFIER_POINTER(name), k_cleanup_label) == 0) {
                *cleanup_bb = bb;
                return label;
            }
        }
    }

    FOR_EACH_BB_FN(bb, cfun) {
        tree label = gimple_block_label(bb);
        tree name = DECL_NAME(label);

        if (name != NULL_TREE
            && strcmp(IDENTIFIER_POINTER(name), k_cleanup_label) == 0) {
            *cleanup_bb = bb;
            return label;
        }
    }

    error("%<eh_autocheck%> function %qE must define label %qs or call %qs",
          current_function_decl,
          k_cleanup_label,
          k_cleanup_marker);
    return NULL_TREE;
}

static void
collect_calls(auto_vec<gimple *> *calls, basic_block cleanup_bb)
{
    basic_block bb = nullptr;

    FOR_EACH_BB_FN(bb, cfun) {
        if (bb == cleanup_bb) {
            continue;
        }

        for (gimple_stmt_iterator gsi = gsi_start_bb(bb);
             !gsi_end_p(gsi);
             gsi_next(&gsi)) {
            gimple *stmt = gsi_stmt(gsi);

            if (!is_gimple_call(stmt)) {
                continue;
            }
            if (gimple_call_noreturn_p(as_a<gcall *>(stmt))) {
                continue;
            }

            calls->safe_push(stmt);
        }
    }
}

static void
insert_check_after_call(gimple *call_stmt, tree error_decl, basic_block cleanup_bb)
{
    basic_block call_bb = gimple_bb(call_stmt);
    edge fallthrough = split_block(call_bb, call_stmt);
    tree zero = build_zero_cst(TREE_TYPE(error_decl));

    gimple_stmt_iterator gsi = gsi_last_bb(call_bb);
    tree error_tmp = create_tmp_var(TREE_TYPE(error_decl), "eh_error_check");
    gassign *load = gimple_build_assign(error_tmp, error_decl);
    gsi_insert_after(&gsi, load, GSI_NEW_STMT);

    gcond *cond = gimple_build_cond(NE_EXPR,
                                    error_tmp,
                                    zero,
                                    NULL_TREE,
                                    NULL_TREE);
    gimple_set_location(cond, gimple_location(call_stmt));
    gsi_insert_after(&gsi, cond, GSI_NEW_STMT);

    fallthrough->flags = EDGE_FALSE_VALUE;
    make_edge(call_bb, cleanup_bb, EDGE_TRUE_VALUE);
}

const pass_data eh_autocheck_pass_data = {
    GIMPLE_PASS,
    "eh_autocheck",
    OPTGROUP_NONE,
    TV_NONE,
    PROP_cfg,
    0,
    0,
    0,
    TODO_cleanup_cfg,
};

class eh_autocheck_pass final : public gimple_opt_pass {
public:
    explicit eh_autocheck_pass(gcc::context *ctxt)
        : gimple_opt_pass(eh_autocheck_pass_data, ctxt)
    {
    }

    bool gate(function *) override
    {
        return function_has_autocheck_attribute();
    }

    unsigned int execute(function *) override
    {
        tree error_decl = find_global_error_decl();
        if (error_decl == NULL_TREE) {
            return 0;
        }

        basic_block cleanup_bb = nullptr;
        tree cleanup_label = find_cleanup_label(&cleanup_bb);
        if (cleanup_label == NULL_TREE || cleanup_bb == nullptr) {
            return 0;
        }

        auto_vec<gimple *> calls;
        collect_calls(&calls, cleanup_bb);

        for (gimple *call_stmt : calls) {
            insert_check_after_call(call_stmt,
                                    error_decl,
                                    cleanup_bb);
        }

        return TODO_cleanup_cfg;
    }
};

static void
register_attributes(void *, void *)
{
    register_attribute(&eh_autocheck_attr);
    register_attribute(&eh_autoreturn_attr);
}

static void
finish_decl(void *event_data, void *)
{
    tree decl = static_cast<tree>(event_data);

    if (decl == NULL_TREE || TREE_CODE(decl) != VAR_DECL) {
        return;
    }

    tree name = DECL_NAME(decl);
    if (name != NULL_TREE
        && strcmp(IDENTIFIER_POINTER(name), k_error_symbol) == 0) {
        global_error_decl = decl;
    }
}

static void
pre_genericize(void *event_data, void *)
{
    tree fndecl = static_cast<tree>(event_data);

    if (fndecl == NULL_TREE || TREE_CODE(fndecl) != FUNCTION_DECL) {
        return;
    }
    if (!function_decl_has_attribute(fndecl, k_autoreturn_attr)) {
        return;
    }

    tree fn_type = TREE_TYPE(fndecl);
    tree return_type = fn_type ? TREE_TYPE(fn_type) : NULL_TREE;

    if (return_type == NULL_TREE || !VOID_TYPE_P(return_type)) {
        error("%<eh_autoreturn%> currently only supports void functions");
        return;
    }

    tree error_decl = find_global_error_decl();
    if (error_decl == NULL_TREE) {
        return;
    }

    tree body = DECL_SAVED_TREE(fndecl);
    if (body == NULL_TREE) {
        return;
    }

    unsigned int inserted = instrument_autoreturn_tree(body, error_decl);
    if (inserted == 0) {
        warning_at(DECL_SOURCE_LOCATION(fndecl),
                   OPT_Wattributes,
                   "%<eh_autoreturn%> function %qE had no instrumentable calls",
                   fndecl);
    }
}

} // namespace

int
plugin_init(plugin_name_args *plugin_info, plugin_gcc_version *version)
{
    if (!plugin_default_version_check(version, &gcc_version)) {
        error("GCC plugin version mismatch");
        return 1;
    }

    register_callback(plugin_info->base_name,
                      PLUGIN_ATTRIBUTES,
                      register_attributes,
                      nullptr);

    register_callback(plugin_info->base_name,
                      PLUGIN_FINISH_DECL,
                      finish_decl,
                      nullptr);

    register_callback(plugin_info->base_name,
                      PLUGIN_PRE_GENERICIZE,
                      pre_genericize,
                      nullptr);

    register_pass_info pass_info;
    pass_info.pass = new eh_autocheck_pass(g);
    pass_info.reference_pass_name = "cfg";
    pass_info.ref_pass_instance_number = 1;
    pass_info.pos_op = PASS_POS_INSERT_AFTER;

    register_callback(plugin_info->base_name,
                      PLUGIN_PASS_MANAGER_SETUP,
                      nullptr,
                      &pass_info);

    return 0;
}
