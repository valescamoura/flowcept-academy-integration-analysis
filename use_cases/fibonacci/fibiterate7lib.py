### for feb 2026 observability demo

### ==== pretend this bit is in the academy standard library ==== ###

import asyncio
import os
from academy.agent import Agent, action
from academy.manager import Manager
from academy.exchange import LocalExchangeFactory, RedisExchangeFactory
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from parsl.concurrent import ParslPoolExecutor
from parsl.config import Config

import logging
logger = logging.getLogger(__name__)

class GeneratorAgent(Agent):
  def __init__(self, g):
    logger.info(f"initialising generator agent {self!r} on {os.getpid()}")
    self.g = g

  @action
  async def next_item(self):
    logger.info(f"in agent-side anext on pid {os.getpid()}")
    # i think this stuff is hanging because the agent process from
    # the above manager never terminates. I'm not sure what the right
    # pattern for that should be.
    logger.info("Awaiting a new value from generator", extra={"academy.agent_id": self.agent_id})
    try:
      return {"done": False, "value": await self.g.__anext__()}
    except StopAsyncIteration:
      return {"done": True, "value": None}


# this is to make a Handle look right for `async for`, which wants
# __aiter__ a non-async, and __anext__ an async that is explicitly
# defined, not implicit like all Handle actions.
# use this on the client side.

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

### ==== pretend this bit is your user code ==== ###

import asyncio
import os

class FibonacciLauncher(Agent):

  @action
  async def calc_fibs(self, init_a, init_b):
     iterator_agent = GeneratorAgent(fibs_generator(init_a, init_b))
     r = await self.agent_launch_alongside(iterator_agent)
     return r

async def fibs_generator(init_a, init_b):
  a = init_a
  b = init_b
  while b < 1000:
    yield b, f"b={b} computed on pid {os.getpid()}"
    t = a+b
    a = b
    b = t
    await asyncio.sleep(0.5)