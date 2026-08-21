import asyncio
import logging
import os
from contextlib import contextmanager

from academy.agent import Agent, action
from flowcept import Flowcept, flowcept_task


logger = logging.getLogger(__name__)


def domain_args_handler(**kwargs):
  return {
      key: value
      for key, value in kwargs.items()
      if key not in {"self", "agent", "generator", "iterator_handle"}
  }


@contextmanager
def flowcept_worker_context():
  workflow_id = os.environ.get("FLOWCEPT_DIRECT_WORKFLOW_ID")
  campaign_id = os.environ.get("FLOWCEPT_DIRECT_CAMPAIGN_ID")
  with Flowcept(
      workflow_id=workflow_id,
      campaign_id=campaign_id,
      workflow_name="academy_fibonacci_direct_code_instrumentation_worker",
      workflow_subtype="academy_fibonacci_worker",
      start_persistence=False,
      check_safe_stops=False,
      save_workflow=False,
  ):
    yield


class GeneratorAgent(Agent):
  def __init__(self, generator):
    logger.info(f"initialising generator agent {self!r} on {os.getpid()}")
    self.generator = generator

  @action
  async def next_item(self):
    logger.info(f"in agent-side anext on pid {os.getpid()}")
    logger.info("Awaiting a new value from generator", extra={"academy.agent_id": self.agent_id})
    with flowcept_worker_context():
      try:
        return await next_fibonacci_item(self.generator)
      except StopAsyncIteration:
        return await end_fibonacci_iteration()


class IteratorShim:
    def __init__(self, handle):
        self.handle = handle

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.handle.next_item()
        if item["done"]:
            raise StopAsyncIteration
        return item["value"]


class FibonacciLauncher(Agent):

  @action
  async def calc_fibs(self, init_a, init_b):
     with flowcept_worker_context():
       return await calc_fibs_instrumented(self, init_a, init_b)


@flowcept_task(
    args_handler=domain_args_handler,
    output_names="iterator_handle",
    tags=["academy", "fibonacci", "agent-action", "domain"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "calc_fibs",
    },
)
async def calc_fibs_instrumented(agent, init_a, init_b):
     iterator_agent = GeneratorAgent(fibs_generator(init_a, init_b))
     return await agent.agent_launch_alongside(iterator_agent)


@flowcept_task(
    args_handler=domain_args_handler,
    tags=["academy", "fibonacci", "agent-action", "domain"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "next_item",
    },
)
async def next_fibonacci_item(generator):
  value = await next_fibonacci_value(generator)
  return {"done": False, "value": value}


@flowcept_task(
    tags=["academy", "fibonacci", "agent-action", "domain"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "instrumented_layer": "agent_domain_code",
        "academy_action": "next_item_stop",
    },
)
async def end_fibonacci_iteration():
  return {"done": True, "value": None}


@flowcept_task(
    args_handler=domain_args_handler,
    tags=["fibonacci", "domain"],
    custom_metadata={
        "approach": "direct_code_instrumentation",
        "instrumented_layer": "domain_generator",
    },
)
async def next_fibonacci_value(generator):
  return await generator.__anext__()


async def fibs_generator(init_a, init_b):
  a = init_a
  b = init_b
  while b < 1000:
    yield b, f"b={b} computed on pid {os.getpid()}"
    t = a + b
    a = b
    b = t
    await asyncio.sleep(0.5)
