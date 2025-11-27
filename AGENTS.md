## Coding style (Python agents)

### Type system

* Always use Python type hints and run a static type checker (`mypy` or `pyright`) on agent code.

  * Functions and methods must have explicit `-> ReturnType` annotations.
  * Public modules in the agent layer should be type-check clean (`--strict` or equivalent) unless there is a clear and documented reason not to.
  * Tests / quick scripts may be less strict, but still must be valid under basic type checking.

---

### Result-based error handling

We standardize on a `Result` type (e.g. [`returns.result.Result`](https://github.com/dry-python/returns)) for **expected / programmable failures**.

```python
from returns.result import Result, Success, Failure

UserResult = Result["User", "UserError"]
```

* For failures that can be reasonably expected, **do not use Python exceptions for control flow**; return a `Result[OkT, ErrE]` instead.

  * When to use `Result` (required)

    * Layers that perform external I/O (HTTP, DB, KV, file system, LLM APIs).
    * Steps in the agent that need to return “success/failure” as part of the protocol (tools, planners, executors).
    * Places where you want to cover business branches exhaustively (no missing `if/elif` branch, no implicit `else: pass`).

  * When it is acceptable **not** to use `Result` (optional)

    * Small, pure helper functions that:

      * fit in a single line or a very small body,
      * have total behavior (no `None` / exceptions), and
      * are only used inside other `Result`-based flows.
    * Trivial formatting / mapping helpers (e.g. `format_user_name(user: User) -> str`).

* Branching on `Result`:

  * Prefer combinators like `.bind()` (like `and_then`) and `.map()` / `.alt()` over manual `if isinstance(...)` when possible.
  * When you must branch manually, do it **once** at the boundary and keep it exhaustive:

    ```python
    from returns.result import Success, Failure

    result = fetch_user(user_id)

    match result:
        case Success(user):
            ...
        case Failure(error):
            ...
    ```

    If you cannot use `match` (older Python), use an `if isinstance(result, Success)` / `Failure` pattern and avoid ad-hoc truthiness checks.

* **Do not represent “absence of value” as `Success(None)`.**

  * Cases like “no search result” or “data does not exist” must be represented as a `Failure` with a dedicated error type (e.g. `UserNotFound`).

  * Do **not** use `Optional[T]` + `None` as a sentinel in `Result[Optional[T], E]` unless there is a very strong reason and it is documented.

  * Any `None` or missing-value behavior from external APIs must be wrapped and normalized into `Result` at a boundary layer.

  * Exception:

    * When an operation’s only purpose is side effects (e.g. sending a notification, emitting a metric) and there is no meaningful success value, use `Result[None, ErrE]` and return `Success(None)` explicitly.

* **Exceptions are not for “programmable failures”.**

  * Exceptions are reserved for:

    * programmer bugs,
    * invariant violations,
    * unrecoverable situations (e.g. “this code path must never be reached”).
  * For normal control flow (expected errors, domain failures), return `Failure(error_value)`.
  * Any “unsafe unwrap” helpers (e.g. `result.unwrap()`) must be used only in tests or invariant checks, not in the main agent logic.

* **Aggregating multiple `Result`s:**

  * When mapping over collections, do not drop partial failures silently.

    ```python
    # Bad: ignores failures
    users = [fetch_user(id).unwrap() for id in ids]  # raises or blows up later

    # Good: collect first error or all errors explicitly
    results = [fetch_user(id) for id in ids]
    aggregated = aggregate_results(results)  # project helper
    ```

  * Provide a helper like `aggregate_results(results: Sequence[Result[T, E]]) -> Result[list[T], E]` or a variant that aggregates all errors into a dedicated `AggregateError`.

* **Creation of Success / Failure** should go through helpers, not direct instantiation.

  * Prefer `Success(value)` / `Failure(error)` (or wrappers like `ok(value)`, `err(error)` in our own helper module) and avoid constructing library internals directly.
  * This eases substitution/testing if we ever swap out the underlying `Result` implementation.

* **Side effects must go through dedicated hooks, not mapping combinators.**

  * Logging, metrics, tracing, and other side effects must be attached via dedicated helpers (e.g. `.tap_success(...)`, `.tap_failure(...)` / wrapper functions), and must **not** be mixed into `.map()` / `.bind()`.

    ```python
    (
        fetch_user(user_id)
        .bind(ensure_active)
        .map(to_dto)  # pure transformation
        .alt(promote_error)  # pure error mapping
        .tap(lambda dto: logger.info("user_loaded", user_id=dto.id))  # side effect only
    )
    ```

  * Inside side-effect callbacks, do not rely on the return value; they should be observational only.

* **Avoid nested `Result` types.**

  * Types like `Result[Result[T, E2], E1]` are forbidden.
  * The inner value must always be a raw domain type (`T`); promotion/aggregation of errors must be done via `alt()` / dedicated mappers.

* **Boundary layers (HTTP handlers, CLIs, workers) must always inspect `Result`.**

  * Convert `Result` into:

    * HTTP status codes + JSON bodies,
    * CLI exit codes + messages,
    * job status / scheduling decisions.
  * Do **not** let domain-level exceptions propagate out of the boundary.
  * Wrap external exceptions (HTTP libraries, DB drivers, cloud SDKs) into domain errors, return as `Failure(...)`, and decide at the boundary whether to retry / log / surface to the caller.

---

### Domain error modeling

* Domain errors must be **typed** and structured; do not return raw strings or integers.

  * Use `dataclasses.dataclass` for payloads and custom error classes or enums for categories.

    ```python
    from dataclasses import dataclass
    from enum import Enum

    class LoginErrorKind(str, Enum):
        INVALID_SESSION = "invalid_session"
        CONFIG_MISSING = "config_missing"
        CUSTOMER_NOT_FOUND = "customer_not_found"
        RATE_LIMITED = "rate_limited"

    @dataclass(frozen=True)
    class LoginError:
        kind: LoginErrorKind
        message: str
        retry_after: int | None = None
        shop_id: str | None = None
    ```

* Each flow should have its own error type, e.g. `LoginFlowError`, `FooFlowError`.

  * Variants (kinds) are named by cause (`ConfigMissing`, `InvalidSession`, etc.).
  * Payload fields are named `<variant>_...` and must have explicit types.

* Error promotion / mapping:

  * In layers that integrate multiple lower-level error types (HTTP, DB, other services), map them to a consolidated flow-level error type using pure functions.

    ```python
    def promote_shopify_error(err: ShopifyError) -> LoginError:
        ...
    ```

  * Do not leak unions of lower-level errors (`Result[T, ShopifyError | CidError | DynamoError]`) to callers; expose only the flow-level error type.

* **Error presentation (public boundaries) must be centralized.**

  * Provide a single presenter (e.g. `present_error(error: LoginError) -> HttpResponsePayload`) that:

    * decides HTTP status codes,
    * serializes machine-readable error codes,
    * formats human-readable messages.
  * Do not duplicate error → HTTP mapping logic across handlers.

---

### Flow composition

* Use a consistent set of combinators:

  * `bind` for chaining operations (`and_then`):

    * `Result[T, E].bind(fn: Callable[[T], Result[U, E]]) -> Result[U, E]`
  * `map` for value-only transformation:

    * `Result[T, E].map(fn: Callable[[T], U]) -> Result[U, E]`
  * `alt` for error promotion / mapping:

    * `Result[T, E1].alt(fn: Callable[[E1], E2]) -> Result[T, E2]`

* When `.bind()` chains become **3 or more steps**, or there are multiple points where the flow can fall into `Failure`, prefer a “collecting” style for readability.

  * For example, define a helper pattern:

    ```python
    from returns.result import Result, Success, Failure

    def run_login_flow(...) -> Result[str, LoginError]:
        # pseudo-code style; actual implementation may vary
        config_result = fetch_config(...)
        if isinstance(config_result, Failure):
            return config_result

        token_result = fetch_token(config_result.unwrap())
        if isinstance(token_result, Failure):
            return token_result

        # ...
        return generate_multipass_url(...)
    ```

  * The exact DSL differs from Ruby’s `Result.collecting`, but the philosophy is the same:
    **“linear, narrative flow, with early exit on failures”.**

* Access to success / error values (`unwrap`-like behavior) must only be used in code paths where the type is established by pattern matching / instance checks.

---

### Agents and tool layers

* For agent tools / skills that perform external I/O:

  * Their public interface must be `Result`-based, not exception-based.
  * The agent planner/executor should consume `Result`s and decide, per error category:

    * whether to retry,
    * whether to surface the error to the user,
    * whether to fall back to an alternative tool.

* **Retries belong to the caller, not to the I/O function.**

  * External I/O helpers should return “reason of failure” (e.g. `LoginError`), not perform internal infinite retries.
  * The caller (agent or job) is responsible for retry policies.
  * Record metrics in error branches (`tap_failure` / logging helpers), and use fallback logic via `.rescue`/`.or_else` only for clearly documented fallback patterns, not as general control flow.

---

### Background jobs / workers and exceptions

We separate how exceptions vs. `Result` are used between **domain/service layers** and **job execution layers** (e.g. Celery workers, custom job runners).

* **Domain / service layers** must keep using `Result` for programmable failures.
  Exceptions are for:

  * invariant violations,
  * impossible states,
  * programming errors.

* **Worker layers** are allowed to raise exceptions as a control signal for the worker framework’s retry mechanism.

  * A worker that directly raises from `perform()` / `run()` signals “this job should be retried based on the worker config”.

* When a worker receives a `Result`, handle it with this policy:

  * **Transient failures (retryable)**
    Examples:

    * temporary HTTP 5xx / network issues,
    * rate limiting / backoff errors,
    * transient token generation failures.

    → In the worker, map these errors to a dedicated exception (`RateLimitedError`, `ExternalServiceError`, etc.) and raise, so the framework’s retry/backoff logic kicks in.

  * **Persistent failures (non-retryable configuration / data problems)**
    Examples:

    * config missing / invalid env vars,
    * missing installation records,
    * permanent decryption failures, etc.

    → Treat as handled:

    * log structured details,
    * emit alerts/metrics,
    * **do not raise**, so the job is considered complete and is not retried forever.
    * If operations explicitly want dead-letter queue behavior, consistently document and implement a dedicated exception + retry/max-retries policy.

* Boundary between exceptions and `Result`:

  * Service code:

    * always returns `Result`,
    * catches external exceptions and maps them to domain errors.
  * Worker code:

    * consumes `Result`,
    * decides per error whether to:

      * log and finish (non-retryable),
      * raise a dedicated exception (retryable).

  → Contract:
  **“exceptions = job framework retry signal, `Result` = domain-level success/failure expression”**.

---

### Linting and style

* Always run a formatter and linter (e.g. `ruff`, `black`, `isort`, `flake8`) on agent code.

  * As an exception, you may disable a rule for specific code only when it is truly necessary and the benefit clearly outweighs the cost.
  * Keep disable scopes as small as possible and document why.

---

### Compatibility and contradictions

* Since this is still in the development phase, you do **not** need to guarantee backward compatibility for data formats or internal APIs.
* If you encounter contradictions in these rules or between code and documentation, **stop and ask** rather than guessing.
  We prefer an explicit design decision over many slightly diverging ad-hoc patterns.
