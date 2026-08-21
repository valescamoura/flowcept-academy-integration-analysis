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
from academy.logging.helpers import log_context
from academy.manager import Manager
from flowcept import Flowcept
from parsl.concurrent import ParslPoolExecutor

from use_cases.fibonacci.fibiterate7lib import FibonacciLauncher, IteratorShim


logger = logging.getLogger(__name__)


async def main():
  from academy.logging.configs.console import ConsoleLogging
  from academy.logging.configs.jsonpool import JSONPoolLogging
  from academy.logging.configs.multi import MultiLogging

  lc = MultiLogging([ConsoleLogging(level=logging.DEBUG, extra=2), JSONPoolLogging()])

  with Flowcept(
      interceptors=["academy_redis_monitor"],
      workflow_name="academy_fibonacci_message_stream_observability",
      workflow_subtype="academy_fibonacci",
      workflow_args={"init_a": 0, "init_b": 1, "limit": 1000},
  ):
   with log_context(lc):
    logger.info(f"start, main process is pid {os.getpid()}")
    logger.info("Academy is configured to use Redis at localhost:6379")

    from parsl.tests.configs.htex_local_alternate import fresh_config
    with ParslPoolExecutor(fresh_config()) as pe:
     async with await Manager.from_exchange_factory(
        factory=RedisExchangeFactory(hostname="localhost", port=6379),
        executors=pe) as m:
      logger.info(f"got manager {m!r}")
      agent = FibonacciLauncher()
      agent_handle = await m.launch(agent, log_config=lc)

      iterator_handle = await agent_handle.calc_fibs(init_a=0, init_b=1)
      assert iterator_handle is not None
      logger.info(f"got iterator handle {iterator_handle}")

      await iterator_handle.ping()

      iterator_shim = IteratorShim(iterator_handle)

      async for item in iterator_shim:
        logger.info(f"Iterator returned: {item}")
        print("Console iterated result: ", item)
        await asyncio.sleep(0.5)

    logger.info("end")


if __name__ == "__main__":
    asyncio.run(main())
