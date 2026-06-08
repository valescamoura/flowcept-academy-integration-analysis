import asyncio
import logging
import os
import sys


def _ensure_project_on_pythonpath() -> None:
  project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
  current = os.environ.get("PYTHONPATH", "")
  paths = [p for p in current.split(os.pathsep) if p]
  if project_dir not in paths:
    os.environ["PYTHONPATH"] = os.pathsep.join([project_dir] + paths)
  if project_dir not in sys.path:
    sys.path.insert(0, project_dir)


_ensure_project_on_pythonpath()

from academy.exchange import RedisExchangeFactory
from academy.logging.helpers import log_context
from academy.manager import Manager
from flowcept import Flowcept, flowcept_task
from parsl.concurrent import ParslPoolExecutor

from fibiterate7lib import FibonacciLauncher, IteratorShim


logger = logging.getLogger(__name__)


def domain_args_handler(**kwargs):
  return {
      key: value
      for key, value in kwargs.items()
      if key not in {"manager", "agent_handle", "iterator_handle", "log_config"}
  }


@flowcept_task(
    output_names="agent_handle",
    args_handler=domain_args_handler,
    tags=["academy", "fibonacci", "agent-launch"],
    custom_metadata={"approach": "direct_code_instrumentation"},
)
async def launch_fibonacci_agent(manager, log_config):
  agent = FibonacciLauncher()
  return await manager.launch(agent, log_config=log_config)


@flowcept_task(
    output_names="ping_result",
    args_handler=domain_args_handler,
    tags=["academy", "fibonacci", "agent-action"],
    custom_metadata={"approach": "direct_code_instrumentation", "academy_action": "ping"},
)
async def ping_iterator(iterator_handle):
  return await iterator_handle.ping()


async def main():
  from academy.logging.configs.console import ConsoleLogging
  from academy.logging.configs.jsonpool import JSONPoolLogging
  from academy.logging.configs.multi import MultiLogging

  lc = MultiLogging([ConsoleLogging(level=logging.DEBUG, extra=2), JSONPoolLogging()])

  with Flowcept(
      workflow_name="academy_fibonacci_direct_code_instrumentation",
      workflow_subtype="academy_fibonacci",
      workflow_args={"init_a": 0, "init_b": 1, "limit": 1000},
  ) as flowcept:
   os.environ["FLOWCEPT_DIRECT_WORKFLOW_ID"] = flowcept.current_workflow_id
   os.environ["FLOWCEPT_DIRECT_CAMPAIGN_ID"] = flowcept.campaign_id
   with log_context(lc):
    logger.info(f"start, main process is pid {os.getpid()}")

    from parsl.tests.configs.htex_local_alternate import fresh_config
    with ParslPoolExecutor(fresh_config()) as pe:
     async with await Manager.from_exchange_factory(
        factory=RedisExchangeFactory(hostname="localhost", port=6379),
        executors=pe) as m:
      logger.info(f"got manager {m!r}")

      agent_handle = await launch_fibonacci_agent(manager=m, log_config=lc)
      iterator_handle = await agent_handle.calc_fibs(init_a=0, init_b=1)
      assert iterator_handle is not None
      logger.info(f"got iterator handle {iterator_handle}")

      await ping_iterator(iterator_handle=iterator_handle)

      iterator_shim = IteratorShim(iterator_handle)

      async for item in iterator_shim:
        logger.info(f"Iterator returned: {item}")
        print("Console iterated result: ", item)
        await asyncio.sleep(0.5)

    logger.info("end")


if __name__ == "__main__":
    asyncio.run(main())
