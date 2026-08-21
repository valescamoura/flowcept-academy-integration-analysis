import asyncio
import json
import logging
import os
import subprocess
import sys
import time
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
from flowcept import AgentObject, Flowcept, FlowceptTask
from flowcept.commons.vocabulary import Status

from instrumented_agents import (
    InstrumentedEvaluatorAgent,
    InstrumentedOrchestratorAgent,
    InstrumentedTrainingWorkerAgent,
)


logger = logging.getLogger(__name__)


async def register_agent(manager, agent_cls, name: str):
    return await manager.register_agent(agent_cls, name=name)


def persist_agent(registration, name: str, workflow_id: str, campaign_id: str) -> None:
    agent = AgentObject(
        agent_id=str(registration.agent_id.uid),
        name=name,
        workflow_id=workflow_id,
        campaign_id=campaign_id,
    )
    agent.extra_metadata = {
        "framework": "academy",
        "approach": "direct_code_instrumentation",
        "use_case": "perceptron_gridsearch",
        "role": name,
    }
    agent.enrich()
    Flowcept.db.insert_or_update_agent(agent)


async def ping_agent(handle):
    return await handle.ping()


def _agent_uid(registration) -> str:
    return str(registration.agent_id.uid)


def _lifecycle_task(
    *,
    activity_id: str,
    registration,
    role: str,
    started_at: float,
    generated: dict | None = None,
    stderr: str | None = None,
    status: Status = Status.FINISHED,
) -> None:
    FlowceptTask(
        workflow_id=os.environ.get("FLOWCEPT_DIRECT_WORKFLOW_ID"),
        campaign_id=os.environ.get("FLOWCEPT_DIRECT_CAMPAIGN_ID"),
        activity_id=activity_id,
        agent_id=_agent_uid(registration),
        used={"agent_role": role},
        generated=generated,
        started_at=started_at,
        ended_at=time.time(),
        stderr=stderr,
        status=status,
        subtype="academy_lifecycle",
        custom_metadata={
            "framework": "academy",
            "approach": "direct_code_instrumentation",
            "use_case": "perceptron_gridsearch",
        },
    )


async def wait_for_agent(handle, registration, role: str, timeout: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        started_at = time.time()
        try:
            await ping_agent(handle)
            _lifecycle_task(
                activity_id="ping",
                registration=registration,
                role=role,
                started_at=started_at,
                generated={"ready": True},
            )
            logger.info("agent is ready", extra={"agent_role": role, "academy.agent_id": handle.agent_id})
            return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {role} ({handle.agent_id}) to respond") from last_error


async def shutdown_agent(handle, registration, role: str) -> None:
    started_at = time.time()
    try:
        await handle.shutdown()
        _lifecycle_task(
            activity_id="shutdown",
            registration=registration,
            role=role,
            started_at=started_at,
            generated={"shutdown_requested": True},
        )
        logger.info("requested agent shutdown", extra={"agent_role": role, "academy.agent_id": handle.agent_id})
    except AgentTerminatedError:
        _lifecycle_task(
            activity_id="shutdown",
            registration=registration,
            role=role,
            started_at=started_at,
            generated={"already_terminated": True},
        )
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
    for process in processes.values():
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

    with Flowcept(
        workflow_name="academy_perceptron_gridsearch_direct_code_instrumentation",
        workflow_subtype="academy_perceptron_gridsearch",
        workflow_args={"n_configs": 5, "checkpoint_check": 10},
    ) as flowcept:
        os.environ["FLOWCEPT_DIRECT_WORKFLOW_ID"] = flowcept.current_workflow_id
        os.environ["FLOWCEPT_DIRECT_CAMPAIGN_ID"] = flowcept.campaign_id

        with log_context(lc):
            logger.info("start academy perceptron gridsearch direct code instrumentation")
            processes = {}
            async with await Manager.from_exchange_factory(
                factory=RedisExchangeFactory(hostname="localhost", port=6379),
            ) as manager:
                training_registration = await register_agent(
                    manager=manager,
                    agent_cls=InstrumentedTrainingWorkerAgent,
                    name="training-worker",
                )
                evaluator_registration = await register_agent(
                    manager=manager,
                    agent_cls=InstrumentedEvaluatorAgent,
                    name="evaluator",
                )
                orchestrator_registration = await register_agent(
                    manager=manager,
                    agent_cls=InstrumentedOrchestratorAgent,
                    name="orchestrator",
                )

                for registration, name in (
                    (training_registration, "training-worker"),
                    (evaluator_registration, "evaluator"),
                    (orchestrator_registration, "orchestrator"),
                ):
                    persist_agent(
                        registration=registration,
                        name=name,
                        workflow_id=flowcept.current_workflow_id,
                        campaign_id=flowcept.campaign_id,
                    )

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

                    await wait_for_agent(training_worker, training_registration, "training_worker")
                    await wait_for_agent(evaluator, evaluator_registration, "evaluator")
                    await wait_for_agent(orchestrator, orchestrator_registration, "orchestrator")

                    summary = await orchestrator.run_gridsearch(
                        artifact_dir=str(artifact_dir.resolve()),
                        n_configs=5,
                        checkpoint_check=10,
                    )
                finally:
                    await shutdown_agent(orchestrator, orchestrator_registration, "orchestrator")
                    await shutdown_agent(training_worker, training_registration, "training_worker")
                    await shutdown_agent(evaluator, evaluator_registration, "evaluator")
                    stop_processes(processes)

            summary_path = Path("perceptron_gridsearch_summary.json")
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
            print(json.dumps(summary, indent=2, sort_keys=True))
            logger.info("end academy perceptron gridsearch direct code instrumentation")


if __name__ == "__main__":
    asyncio.run(main())
