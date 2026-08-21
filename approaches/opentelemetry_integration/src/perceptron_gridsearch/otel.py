from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from openinference.instrumentation.academy import AcademyInstrumentor


def configure_openinference() -> tuple[TracerProvider, AcademyInstrumentor]:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:14317")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "academy-openinference-perceptron-gridsearch")
    campaign_id = os.environ.get("FLOWCEPT_CAMPAIGN_ID", service_name)

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "openinference.project.name": service_name,
                "flowcept.campaign_id": campaign_id,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                insecure=os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true",
            )
        )
    )
    trace.set_tracer_provider(provider)

    instrumentor = AcademyInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    return provider, instrumentor


def shutdown_openinference(provider: TracerProvider, instrumentor: AcademyInstrumentor) -> None:
    instrumentor.uninstrument()
    provider.force_flush(timeout_millis=10_000)
    provider.shutdown()
