"""Wires routers and shared objects into a Dispatcher."""
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .config import Config
from .handlers import owner, shop
from .repo import Repo


def build_dispatcher(cfg: Config, repo: Repo) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp["cfg"], dp["repo"] = cfg, repo
    dp.include_routers(owner.router, shop.router)
    return dp
