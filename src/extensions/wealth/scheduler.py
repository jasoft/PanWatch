"""每日净资产快照调度器。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.extensions.wealth.service import (
    default_benchmark_price,
    now_shanghai_date,
    record_snapshot,
)
from src.web.database import SessionLocal

logger = logging.getLogger(__name__)


class WealthSnapshotScheduler:
    """工作日 23:10 记录当日净资产和基准收盘价。

    Google Sheets 的 ``main`` 触发器约 22:49 启动；预留 21 分钟，避免在表格
    刷新尚未完成时读到前一交易日的 Worker 快照。
    """

    def __init__(self, timezone: str = "Asia/Shanghai"):
        self.timezone = timezone
        self.scheduler = AsyncIOScheduler(timezone=timezone)

    def start(self) -> None:
        self.scheduler.add_job(
            self.run_once,
            CronTrigger(
                day_of_week="mon-fri",
                hour=23,
                minute=10,
                timezone=self.timezone,
            ),
            id="wealth_daily_snapshot",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self.scheduler.start()
        logger.info("全资产每日快照调度器已启动（工作日 23:10）")

    def run_once(self) -> None:
        db = SessionLocal()
        try:
            try:
                from src.extensions.wealth.relay import sync_from_relay

                sync_from_relay(db)
                logger.info("全资产快照前已同步 Google Sheets 当日数据")
            except Exception as exc:
                logger.warning("Google Sheets 中继同步失败，继续使用本地资产: %s", exc)
            snapshot = record_snapshot(
                db,
                snapshot_date=now_shanghai_date(),
                benchmark_price_provider=default_benchmark_price,
            )
            logger.info(
                "全资产快照完成: %s 净资产 %.2f",
                snapshot.snapshot_date,
                snapshot.net_assets,
            )
        except Exception:
            db.rollback()
            logger.exception("全资产快照失败")
        finally:
            db.close()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("全资产每日快照调度器已关闭")
