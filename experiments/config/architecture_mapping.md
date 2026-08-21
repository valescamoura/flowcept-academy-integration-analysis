# Architecture Mapping

| Approach | Capture Point | Intrusiveness | Coupling | Deployment Complexity | Best Fit |
|---|---|---|---|---|---|
| Direct Application Instrumentation | Application source code | High | Application implementation and provenance API | Low | Precise domain dataflow and explicit task semantics when code changes are acceptable |
| Log Handler-based Observability | Structured event logs | Low | Log schema and parser/handler mapping | Low | Retrofitting provenance from existing structured execution logs |
| Dynamic Framework Instrumentation | Framework runtime behavior | Medium | Framework internals and runtime extension points | Medium | Capturing actions, lifecycle, and delegation without changing application code |
| Direct Framework Instrumentation | Framework-native provenance layer | Medium | Framework provenance model and target provenance schema | Low | Framework-owned provenance with first-class execution and agent semantics |
| Message Stream Observability | Inter-component message stream | Low-Medium | Message protocol and broker visibility | Medium | Observing communication, request/response pairs, and distributed interactions externally |
| Third-party Adapters | Standard observability traces/events | Low-Medium | Telemetry semantic conventions and collector/exporter mapping | High | Standards-based observability and interoperability with telemetry ecosystems |
