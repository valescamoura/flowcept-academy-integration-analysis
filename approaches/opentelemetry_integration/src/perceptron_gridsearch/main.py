from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path


def _ensure_project_on_pythonpath() -> Path:
    project_dir = Path(__file__).resolve().parents[4]
    current = os.environ.get("PYTHONPATH", "")
    paths = [path for path in current.split(os.pathsep) if path]
    if str(project_dir) not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([str(project_dir), *paths])
    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))
    return project_dir


REPO_ROOT = _ensure_project_on_pythonpath()

from academy.exchange import RedisExchangeFactory
from academy.exception import AgentTerminatedError
from academy.logging.helpers import log_context
from academy.manager import Manager

from approaches.opentelemetry_integration.src.perceptron_gridsearch.otel import (
    configure_openinference,
    shutdown_openinference,
)
from use_cases.perceptron_gridsearch.academy_agents import (
    EvaluatorAgent,
    OrchestratorAgent,
    TrainingWorkerAgent,
)


logger = logging.getLogger(__name__)
SERVICE_NAME = "academy-openinference-perceptron-gridsearch"


async def wait_for_agent(handle, role: str, timeout: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            await handle.ping()
            logger.info("agent is ready", extra={"agent_role": role, "academy.agent_id": handle.agent_id})
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {role} ({handle.agent_id}) to respond") from last_error


async def shutdown_agent(handle, role: str) -> None:
    try:
        await handle.shutdown()
        logger.info("requested agent shutdown", extra={"agent_role": role, "academy.agent_id": handle.agent_id})
    except AgentTerminatedError:
        logger.info("agent already terminated", extra={"agent_role": role, "academy.agent_id": handle.agent_id})


def default_collector_dir() -> Path:
    # Test against the local collector checkout while the exporter changes are not released.
    # To go back to the remote branch flow later, set OTEL_COLLECTOR_DIR to a cloned
    # opentelemetry-collector/cmd/otelcorecol from:
    # https://github.com/valescamoura/opentelemetry-collector/tree/flowcept_academy_exporter
    return REPO_ROOT.parent / "valescamoura" / "opentelemetry-collector" / "cmd" / "otelcorecol"


def start_agent_process(role: str, registration, *extra_args: str) -> subprocess.Popen:
    command = [
        sys.executable,
        "run_agent.py",
        "--role",
        role,
        "--registration-json",
        registration.model_dump_json(),
        *extra_args,
    ]
    process = subprocess.Popen(command)
    logger.info(
        "started agent subprocess",
        extra={"agent_role": role, "academy.agent_id": registration.agent_id, "pid": process.pid},
    )
    return process


def stop_agent_processes(processes: dict[str, subprocess.Popen]) -> None:
    for process in processes.values():
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    for role, process in processes.items():
        if process.poll() is None:
            logger.info("terminating leftover agent subprocess", extra={"agent_role": role, "pid": process.pid})
            process.terminate()
    for role, process in processes.items():
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("killing stuck agent subprocess", extra={"agent_role": role, "pid": process.pid})
            process.kill()


async def run_workflow() -> dict:
    from academy.logging.configs.console import ConsoleLogging

    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)
    log_config = ConsoleLogging(level=logging.DEBUG, extra=2)

    with log_context(log_config):
        logger.info("start academy perceptron gridsearch opentelemetry integration")
        processes = {}
        async with await Manager.from_exchange_factory(
            factory=RedisExchangeFactory(hostname="localhost", port=6379),
        ) as manager:
            training_registration = await manager.register_agent(TrainingWorkerAgent, name="training-worker")
            evaluator_registration = await manager.register_agent(EvaluatorAgent, name="evaluator")
            orchestrator_registration = await manager.register_agent(OrchestratorAgent, name="orchestrator")

            training_worker = manager.get_handle(training_registration)
            evaluator = manager.get_handle(evaluator_registration)
            orchestrator = manager.get_handle(orchestrator_registration)

            try:
                processes["training_worker"] = start_agent_process("training_worker", training_registration)
                processes["evaluator"] = start_agent_process("evaluator", evaluator_registration)
                processes["orchestrator"] = start_agent_process(
                    "orchestrator",
                    orchestrator_registration,
                    "--training-worker-id-json",
                    training_registration.agent_id.model_dump_json(),
                    "--evaluator-id-json",
                    evaluator_registration.agent_id.model_dump_json(),
                )

                await wait_for_agent(training_worker, "training_worker")
                await wait_for_agent(evaluator, "evaluator")
                await wait_for_agent(orchestrator, "orchestrator")
                return await orchestrator.run_gridsearch(
                    artifact_dir=str(artifact_dir.resolve()),
                    n_configs=5,
                    checkpoint_check=10,
                )
            finally:
                await shutdown_agent(orchestrator, "orchestrator")
                await shutdown_agent(training_worker, "training_worker")
                await shutdown_agent(evaluator, "evaluator")
                stop_agent_processes(processes)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:14317")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_INSECURE", "true")
    os.environ.setdefault("OTEL_SERVICE_NAME", SERVICE_NAME)
    os.environ.setdefault("FLOWCEPT_CAMPAIGN_ID", SERVICE_NAME)

    provider = None
    instrumentor = None
    try:
        provider, instrumentor = configure_openinference()
        summary = await run_workflow()

        summary_path = Path("perceptron_gridsearch_summary.json")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        logger.info("end academy perceptron gridsearch opentelemetry integration")
    finally:
        if provider is not None and instrumentor is not None:
            shutdown_openinference(provider, instrumentor)


if __name__ == "__main__":
    asyncio.run(main())
