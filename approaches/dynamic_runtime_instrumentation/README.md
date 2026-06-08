## Dynamic Runtime Instrumentation

This approach uses the `agentic` branch of
`GueroudjiAmal/flowcept`, which provides an Academy plugin that monkey-patches
`academy.runtime.Runtime` at runtime.

The Fibonacci use case code is intentionally close to the baseline. The capture
logic is not embedded in `fibiterate7.py`; it is enabled through Flowcept's
settings:

```yaml
plugins:
  academy:
    enabled: true
    kind: academy
    workflow_name: academy_fibonacci_dynamic_runtime_instrumentation
    performance_tracking: true
```

Expected behavior:

- Flowcept starts normally from the driver script.
- The Academy plugin starts automatically from `settings.yaml`.
- The plugin patches Academy runtime methods.
- Academy action, loop, and lifecycle events are emitted as Flowcept tasks.

The upstream example for this plugin uses `LocalExchangeFactory` and
`ThreadPoolExecutor`. This approach follows that execution model because the
plugin patches Academy's in-process `Runtime` class. With the common
`RedisExchangeFactory` + `ParslPoolExecutor` setup, the agent runtime executes
inside Parsl worker processes where the plugin's active interceptor is not
propagated by this Flowcept branch, so workflows are created but action tasks
are not captured.

This is an important evaluation boundary for the approach: the monkey-patching
implementation is effective for in-process Academy runtimes, but it is not
currently Parsl-aware.
