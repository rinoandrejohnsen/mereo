#include <coroutine>
#include <iostream>
#include <optional>
#include <string_view>
#include <utility>

enum class error_code {
    read_failed,
};

enum class handler_decision {
    resume_with_fallback,
    cleanup,
};

struct error_interrupt {
    error_code code;
    std::string_view message;
};

static std::string_view error_name(error_code code)
{
    switch (code) {
    case error_code::read_failed:
        return "read_failed";
    }

    return "unknown";
}

struct resource {
    explicit resource(std::string_view name)
        : name_(name)
    {
        std::cout << "acquire " << name_ << '\n';
    }

    resource(const resource &) = delete;
    resource &operator=(const resource &) = delete;

    ~resource()
    {
        std::cout << "release " << name_ << '\n';
    }

private:
    std::string_view name_;
};

class interruptible_task {
public:
    struct promise_type {
        std::optional<error_interrupt> pending_interrupt;
        int returned_value = 0;

        interruptible_task get_return_object()
        {
            return interruptible_task{
                std::coroutine_handle<promise_type>::from_promise(*this)
            };
        }

        std::suspend_always initial_suspend() noexcept
        {
            return {};
        }

        std::suspend_always final_suspend() noexcept
        {
            return {};
        }

        std::suspend_always yield_value(error_interrupt interrupt) noexcept
        {
            pending_interrupt = interrupt;
            return {};
        }

        void return_value(int value) noexcept
        {
            returned_value = value;
        }

        void unhandled_exception()
        {
            std::terminate();
        }
    };

    enum class step_kind {
        interrupted,
        returned,
        done,
    };

    struct step {
        step_kind kind;
        std::optional<error_interrupt> interrupt;
        int value = 0;
    };

    explicit interruptible_task(std::coroutine_handle<promise_type> handle)
        : handle_(handle)
    {
    }

    interruptible_task(const interruptible_task &) = delete;
    interruptible_task &operator=(const interruptible_task &) = delete;

    interruptible_task(interruptible_task &&other) noexcept
        : handle_(std::exchange(other.handle_, {}))
    {
    }

    interruptible_task &operator=(interruptible_task &&other) noexcept
    {
        if (this != &other) {
            destroy();
            handle_ = std::exchange(other.handle_, {});
        }
        return *this;
    }

    ~interruptible_task()
    {
        destroy();
    }

    step resume()
    {
        if (!handle_ || handle_.done()) {
            return {
                .kind = step_kind::done,
                .interrupt = std::nullopt,
                .value = 0,
            };
        }

        promise_type &promise = handle_.promise();
        promise.pending_interrupt.reset();

        handle_.resume();

        if (promise.pending_interrupt.has_value()) {
            return {
                .kind = step_kind::interrupted,
                .interrupt = promise.pending_interrupt,
                .value = 0,
            };
        }

        if (handle_.done()) {
            return {
                .kind = step_kind::returned,
                .interrupt = std::nullopt,
                .value = promise.returned_value,
            };
        }

        return {
            .kind = step_kind::done,
            .interrupt = std::nullopt,
            .value = 0,
        };
    }

    void destroy() noexcept
    {
        if (handle_) {
            handle_.destroy();
            handle_ = {};
        }
    }

private:
    std::coroutine_handle<promise_type> handle_;
};

static handler_decision handle_error(
    const error_interrupt &interrupt,
    bool allow_fallback)
{
    std::cout << "handler: interrupt "
              << error_name(interrupt.code)
              << ": " << interrupt.message << '\n';

    if (allow_fallback) {
        std::cout << "handler: resume coroutine with fallback\n";
        return handler_decision::resume_with_fallback;
    }

    std::cout << "handler: cleanup suspended coroutine\n";
    return handler_decision::cleanup;
}

static interruptible_task load_config_value()
{
    resource file("config file");
    resource buffer("read buffer");

    std::cout << "task: read primary config\n";

    co_yield error_interrupt{
        .code = error_code::read_failed,
        .message = "primary config is unavailable",
    };

    std::cout << "task: resumed after interrupt; using fallback config\n";
    co_return 42;
}

static void run_case(std::string_view label, bool allow_fallback)
{
    std::cout << "\n-- " << label << " --\n";

    interruptible_task task = load_config_value();
    interruptible_task::step step = task.resume();

    if (step.kind != interruptible_task::step_kind::interrupted) {
        std::cout << "driver: expected interrupt\n";
        return;
    }

    handler_decision decision = handle_error(*step.interrupt, allow_fallback);

    if (decision == handler_decision::cleanup) {
        task.destroy();
        std::cout << "driver: task destroyed after interrupt\n";
        return;
    }

    step = task.resume();
    if (step.kind == interruptible_task::step_kind::returned) {
        std::cout << "driver: task returned " << step.value << '\n';
    }
}

int main()
{
    run_case("handler resumes", true);
    run_case("handler cleans up", false);
    return 0;
}
