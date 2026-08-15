#include "benchmark.h"

#include <inttypes.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

/*
 * Strategy: use one cleanup label for functions that acquire resources.
 * This keeps each failure branch short and avoids duplicated free/close logic.
 */

typedef enum parse_status {
    PARSE_OK = 0,
    PARSE_EMPTY,
    PARSE_BAD_CHAR,
    PARSE_OVERFLOW,
    PARSE_NO_MEMORY,
} parse_status;

static const char *parse_status_name(parse_status status)
{
    switch (status) {
    case PARSE_OK:
        return "ok";
    case PARSE_EMPTY:
        return "empty";
    case PARSE_BAD_CHAR:
        return "bad char";
    case PARSE_OVERFLOW:
        return "overflow";
    case PARSE_NO_MEMORY:
        return "no memory";
    }

    return "unknown";
}

static parse_status parse_u32_status(const char *text, uint32_t *out)
{
    const unsigned char *p = (const unsigned char *)text;
    uint32_t value = 0;

    if (unlikely(*p == '\0')) {
        return PARSE_EMPTY;
    }

    do {
        unsigned digit = (unsigned)(*p - '0');

        if (unlikely(digit > 9u)) {
            return PARSE_BAD_CHAR;
        }
        if (unlikely(value > (UINT32_MAX - digit) / 10u)) {
            return PARSE_OVERFLOW;
        }

        value = value * 10u + digit;
        ++p;
    } while (*p != '\0');

    *out = value;
    return PARSE_OK;
}

static parse_status parse_batch_owned(
    const char *const *items,
    size_t count,
    uint32_t **out_values,
    size_t *out_count)
{
    parse_status status = PARSE_OK;
    uint32_t *values = NULL;

    *out_values = NULL;
    *out_count = 0;

    if (count > SIZE_MAX / sizeof(*values)) {
        status = PARSE_NO_MEMORY;
        goto cleanup;
    }

    values = malloc(count * sizeof(*values));
    if (values == NULL && count != 0) {
        status = PARSE_NO_MEMORY;
        goto cleanup;
    }

    for (size_t i = 0; i < count; ++i) {
        status = parse_u32_status(items[i], &values[i]);
        if (unlikely(status != PARSE_OK)) {
            goto cleanup;
        }
    }

    *out_values = values;
    *out_count = count;
    values = NULL;

cleanup:
    free(values);
    return status;
}

int main(void)
{
    static const char *const good_items[] = {
        "1",
        "20",
        "300",
        "4000",
    };
    static const char *const bad_items[] = {
        "1",
        "20x",
        "300",
        "4000",
    };

    uint32_t *values = NULL;
    size_t count = 0;
    int exit_code = 0;
    parse_status status = parse_batch_owned(
        good_items,
        sizeof(good_items) / sizeof(good_items[0]),
        &values,
        &count);

    if (status == PARSE_OK) {
        printf("demo: parsed %zu values first=%" PRIu32 " last=%" PRIu32 "\n",
               count,
               values[0],
               values[count - 1]);
    } else {
        printf("demo: good batch failed -> %s\n", parse_status_name(status));
        exit_code = 1;
    }
    free(values);

    values = NULL;
    count = 0;
    status = parse_batch_owned(
        bad_items,
        sizeof(bad_items) / sizeof(bad_items[0]),
        &values,
        &count);

    printf("demo: bad batch -> %s, returned_count=%zu\n",
           parse_status_name(status),
           count);
    if (status == PARSE_OK || count != 0) {
        exit_code = 1;
    }
    free(values);

    return exit_code;
}
