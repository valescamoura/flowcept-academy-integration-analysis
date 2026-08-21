import argparse
import asyncio
import logging
import os
import sys


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
from academy.exchange.redis import RedisAgentRegistration
from academy.handle import Handle
from academy.identifier import AgentId
from academy.logging.helpers import log_context
from academy.runtime import Runtime

from instrumented_agents import (
    InstrumentedEvaluatorAgent,
    InstrumentedOrchestratorAgent,
    InstrumentedTrainingWorkerAgent,
)


logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Run one instrumented Academy Perceptron GridSearch agent process.")
    parser.add_argument("--role", choices=["training_worker", "evaluator", "orchestrator"], required=True)
    parser.add_argument("--registration-json", required=True)
    parser.add_argument("--training-worker-id-json")
    parser.add_argument("--evaluator-id-json")
    return parser.parse_args()


def build_agent(args):
    if args.role == "training_worker":
        return InstrumentedTrainingWorkerAgent()
    if args.role == "evaluator":
        return InstrumentedEvaluatorAgent()
    if not args.training_worker_id_json or not args.evaluator_id_json:
        raise ValueError("orchestrator requires --training-worker-id-json and --evaluator-id-json")
    training_worker = Handle(AgentId.model_validate_json(args.training_worker_id_json))
    evaluator = Handle(AgentId.model_validate_json(args.evaluator_id_json))
    return InstrumentedOrchestratorAgent(training_worker=training_worker, evaluator=evaluator)


async def main():
    from academy.logging.configs.console import ConsoleLogging

    args = parse_args()
    registration = RedisAgentRegistration.model_validate_json(args.registration_json)
    agent = build_agent(args)
    lc = ConsoleLogging(level=logging.DEBUG, extra=2)

    with log_context(lc):
        logger.info(
            "starting instrumented agent process",
            extra={
                "academy.agent_id": registration.agent_id,
                "agent_role": args.role,
                "pid": os.getpid(),
            },
        )
        async with Runtime(
            agent,
            exchange_factory=RedisExchangeFactory(hostname="localhost", port=6379),
            registration=registration,
        ) as runtime:
            await runtime.wait_shutdown()
        logger.info(
            "stopped instrumented agent process",
            extra={
                "academy.agent_id": registration.agent_id,
                "agent_role": args.role,
                "pid": os.getpid(),
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
