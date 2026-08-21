import asyncio
import logging
import os

from academy.agent import Agent, action


logger = logging.getLogger(__name__)


class FlowceptWorkerMixin:
    async def agent_on_startup(self) -> None:
        campaign_id = os.environ.get("FLOWCEPT_CAMPAIGN_ID")
        self._flowcept_academy_interceptor = None
        if not campaign_id:
            return

        try:
            import flowcept.agents.academy.academy_plugin as academy_plugin
            from flowcept.agents.academy.academy_plugin import (
                AcademyInterceptor,
                _install_runtime_patches,
            )

            workflow_name = f"academy-fibonacci-{type(self).__name__}-{os.getpid()}"
            interceptor = AcademyInterceptor()
            interceptor.start(workflow_name, campaign_id=campaign_id)
            academy_plugin._ACTIVE_INTERCEPTOR = interceptor
            _install_runtime_patches()
            self._flowcept_academy_interceptor = interceptor
            logger.info("Flowcept Academy interceptor enabled in worker pid %s", os.getpid())
        except Exception as exc:
            logger.warning("Flowcept Academy interceptor setup failed in worker: %s", exc)

    async def agent_on_shutdown(self) -> None:
        interceptor = getattr(self, "_flowcept_academy_interceptor", None)
        if interceptor is not None:
            try:
                interceptor.stop()
            except Exception as exc:
                logger.warning("Flowcept Academy interceptor shutdown failed in worker: %s", exc)


class GeneratorAgent(FlowceptWorkerMixin, Agent):
    def __init__(self, g):
        logger.info(f"initialising generator agent {self!r} on {os.getpid()}")
        self.g = g

    @action
    async def next_item(self):
        logger.info(f"in agent-side anext on pid {os.getpid()}")
        logger.info("Awaiting a new value from generator", extra={"academy.agent_id": self.agent_id})
        try:
            return {"done": False, "value": await self.g.__anext__()}
        except StopAsyncIteration:
            return {"done": True, "value": None}


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


class FibonacciLauncher(FlowceptWorkerMixin, Agent):
    @action
    async def calc_fibs(self, init_a, init_b):
        iterator_agent = GeneratorAgent(fibs_generator(init_a, init_b))
        result = await self.agent_launch_alongside(iterator_agent)
        return result


async def fibs_generator(init_a, init_b):
    a = init_a
    b = init_b
    while b < 1000:
        yield b, f"b={b} computed on pid {os.getpid()}"
        t = a + b
        a = b
        b = t
        await asyncio.sleep(0.5)
