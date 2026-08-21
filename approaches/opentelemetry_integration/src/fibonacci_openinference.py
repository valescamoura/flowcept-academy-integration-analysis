import asyncio
import logging
import os
import sys

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from openinference.instrumentation.academy import AcademyInstrumentor


def _ensure_project_on_pythonpath() -> None:
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    current = os.environ.get("PYTHONPATH", "")
    paths = [p for p in current.split(os.pathsep) if p]
    if project_dir not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([project_dir] + paths)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)


_ensure_project_on_pythonpath()

from academy.agent import Agent, action
from academy.exchange import LocalExchangeFactory
from academy.handle import Handle
from academy.runtime import Runtime


logger = logging.getLogger(__name__)


class FibonacciWorker(Agent):
    @action
    async def next_fibonacci(self, a: int, b: int) -> dict[str, int]:
        await asyncio.sleep(0.05)
        return {"a": b, "b": a + b, "value": b}


class FibonacciCoordinator(Agent):
    worker_agent_id = None

    @action
    async def generate(self, limit: int = 1000) -> list[int]:
        if self.worker_agent_id is None:
            raise RuntimeError("FibonacciCoordinator.worker_agent_id was not configured.")
        worker_handle: Handle[FibonacciWorker] = Handle(self.worker_agent_id)
        values: list[int] = []
        a, b = 0, 1
        while b < limit:
            result = await worker_handle.next_fibonacci(a, b)
            values.append(result["value"])
            a = result["a"]
            b = result["b"]
        return values


def configure_openinference() -> tuple[TracerProvider, AcademyInstrumentor]:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:14317")
    campaign_id = os.environ.get("FLOWCEPT_CAMPAIGN_ID", "academy-openinference-fibonacci")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "academy-openinference-fibonacci")

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
                insecure=os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower()
                == "true",
            )
        )
    )
    trace.set_tracer_provider(provider)

    instrumentor = AcademyInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    return provider, instrumentor


async def run_fibonacci(limit: int) -> list[int]:
    factory = LocalExchangeFactory()
    async with await factory.create_user_client(start_listener=True) as user_client:
        worker_registration = await user_client.register_agent(FibonacciWorker)
        FibonacciCoordinator.worker_agent_id = worker_registration.agent_id
        coordinator_registration = await user_client.register_agent(FibonacciCoordinator)

        worker_runtime = Runtime(
            FibonacciWorker(),
            exchange_factory=factory,
            registration=worker_registration,
        )
        coordinator_runtime = Runtime(
            FibonacciCoordinator(),
            exchange_factory=factory,
            registration=coordinator_registration,
        )

        async with worker_runtime, coordinator_runtime:
            coordinator_handle: Handle[FibonacciCoordinator] = Handle(
                coordinator_registration.agent_id,
                exchange=user_client,
                ignore_context=True,
            )
            values = await coordinator_handle.generate(limit=limit)

            coordinator_runtime.signal_shutdown()
            worker_runtime.signal_shutdown()
            await coordinator_runtime.wait_shutdown(timeout=1)
            await worker_runtime.wait_shutdown(timeout=1)
            return values


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    limit = int(os.environ.get("FIBONACCI_LIMIT", "1000"))
    provider, instrumentor = configure_openinference()
    try:
        values = await run_fibonacci(limit)
        print(f"Fibonacci values below {limit}: {values}")
    finally:
        instrumentor.uninstrument()
        provider.force_flush()
        provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
