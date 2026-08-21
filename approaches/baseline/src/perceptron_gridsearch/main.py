import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path


def _ensure_project_on_pythonpath() -> None:
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    current = os.environ.get("PYTHONPATH", "")
    paths = [p for p in current.split(os.pathsep) if p]
    if project_dir not in paths:
        os.environ["PYTHONPATH"] = os.pathsep.join([project_dir] + paths)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)


_ensure_project_on_pythonpath()

from academy.exchange import RedisExchangeFactory
from academy.exception import AgentTerminatedError
from academy.logging.helpers import log_context
from academy.manager import Manager

from use_cases.perceptron_gridsearch.academy_agents import (
    EvaluatorAgent,
    OrchestratorAgent,
    TrainingWorkerAgent,
)


logger = logging.getLogger(__name__)


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
    logger.info("starting agent subprocess", extra={"agent_role": role, "academy.agent_id": registration.agent_id})
    return subprocess.Popen(command)


def stop_processes(processes: dict[str, subprocess.Popen]) -> None:
    for role, process in processes.items():
        if process.poll() is not None:
            continue
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


async def main():
    from academy.logging.configs.console import ConsoleLogging

    lc = ConsoleLogging(level=logging.DEBUG, extra=2)
    artifact_dir = Path("artifacts")
    artifact_dir.mkdir(exist_ok=True)

    with log_context(lc):
        logger.info("start academy perceptron gridsearch baseline")
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

                summary = await orchestrator.run_gridsearch(
                    artifact_dir=str(artifact_dir.resolve()),
                    n_configs=5,
                    checkpoint_check=10,
                )
            finally:
                await shutdown_agent(orchestrator, "orchestrator")
                await shutdown_agent(training_worker, "training_worker")
                await shutdown_agent(evaluator, "evaluator")
                stop_processes(processes)

        summary_path = Path("perceptron_gridsearch_summary.json")
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        logger.info("end academy perceptron gridsearch baseline")


if __name__ == "__main__":
    asyncio.run(main())
