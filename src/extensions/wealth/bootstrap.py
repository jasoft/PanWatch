"""全资产扩展生命周期入口。"""

from __future__ import annotations

import logging

from src.config import Settings
from src.extensions.wealth.scheduler import WealthSnapshotScheduler

logger = logging.getLogger(__name__)
_scheduler: WealthSnapshotScheduler | None = None


def start_wealth_extension() -> None:
    """启动扩展后台任务；重复调用安全。"""

    global _scheduler
    if _scheduler is not None:
        return
    settings = Settings()
    _scheduler = WealthSnapshotScheduler(timezone=settings.app_timezone)
    _scheduler.start()


def stop_wealth_extension() -> None:
    """停止扩展后台任务。"""

    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown()
    finally:
        _scheduler = None
