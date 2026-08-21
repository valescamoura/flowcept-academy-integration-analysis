### for feb 2026 observability demo

### ==== pretend this bit is in the academy standard library ==== ###

import asyncio
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

from academy.agent import Agent, action
from academy.manager import Manager
from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from parsl.concurrent import ParslPoolExecutor
from parsl.config import Config

from use_cases.fibonacci.fibiterate7lib import FibonacciLauncher, IteratorShim
from flowcepthandler import FlowceptLogging

from academy.logging.helpers import log_context

import logging
logger = logging.getLogger(__name__)

async def main():

  from academy.logging.configs.console import ConsoleLogging
  from academy.logging.configs.jsonpool import JSONPoolLogging
  from academy.logging.configs.multi import MultiLogging

  flc = FlowceptLogging()
  _ensure_project_on_pythonpath()

  lc = MultiLogging([flc, ConsoleLogging(level=logging.DEBUG, extra=2), JSONPoolLogging()])

  # initialize logging locally, until the end of the process
  with log_context(lc):

   logger.info(f"start, main process is pid {os.getpid()}")

   from parsl.tests.configs.htex_local_alternate import fresh_config
   with ParslPoolExecutor(fresh_config()) as pe:

    async with await Manager.from_exchange_factory(
       factory=RedisExchangeFactory(hostname='localhost', port=6379),
        executors=pe) as m:
     logger.info(f"got manager {m!r}")
     a = FibonacciLauncher()
     ah = await m.launch(a, log_config=lc)

     iteratorh = await ah.calc_fibs(init_a=0, init_b=1)
     assert iteratorh is not None
     logger.info(f"got iterator handle {iteratorh}")

     await iteratorh.ping()

     iterator_shim = IteratorShim(iteratorh)

     async for n in iterator_shim:
       logger.info(f"Iterator returned: {n}")
       print("Console iterated result: ", n)
       await asyncio.sleep(0.5)

   logger.info("end")


if __name__ == "__main__":
    asyncio.run(main())
