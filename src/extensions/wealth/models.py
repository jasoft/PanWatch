"""全资产扩展 ORM 模型。

这些表刻意不修改 PanWatch 上游的 ``stocks`` / ``positions`` 表。上游持仓继续
负责股票监控与 Agent 上下文；本扩展负责跨品类净资产、衍生品敞口和历史净值。
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from src.web.database import Base


class WealthAsset(Base):
    """一项可估值资产、负债或衍生品账户权益。"""

    __tablename__ = "wealth_assets"
    __table_args__ = (
        UniqueConstraint("source_system", "source_key", name="uq_wealth_asset_source"),
        Index("ix_wealth_assets_category_enabled", "category", "enabled"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False, default="默认账户")
    category = Column(String, nullable=False)
    symbol = Column(String, nullable=False, default="")
    name = Column(String, nullable=False)
    market = Column(String, nullable=False, default="")
    currency = Column(String, nullable=False, default="CNY")
    exchange_rate = Column(Float, nullable=False, default=1.0)

    valuation_method = Column(String, nullable=False, default="price")
    quantity = Column(Float, nullable=False, default=0.0)
    current_price = Column(Float, nullable=True)
    cost_price = Column(Float, nullable=True)
    manual_amount = Column(Float, nullable=True)
    contract_multiplier = Column(Float, nullable=False, default=1.0)
    position_side = Column(String, nullable=False, default="long")
    margin = Column(Float, nullable=True)

    enabled = Column(Boolean, nullable=False, default=True)
    source_system = Column(String, nullable=False, default="manual")
    source_key = Column(String, nullable=False)
    price_as_of = Column(String, nullable=False, default="")
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WealthSnapshot(Base):
    """每日净资产与基准快照。"""

    __tablename__ = "wealth_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", name="uq_wealth_snapshot_date"),
        Index("ix_wealth_snapshot_date", "snapshot_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(String, nullable=False)
    gross_assets = Column(Float, nullable=False, default=0.0)
    liabilities = Column(Float, nullable=False, default=0.0)
    net_assets = Column(Float, nullable=False, default=0.0)
    derivative_exposure = Column(Float, nullable=False, default=0.0)
    leverage = Column(Float, nullable=False, default=0.0)
    external_flow = Column(Float, nullable=False, default=0.0)
    unit_count = Column(Float, nullable=True)
    performance_nav = Column(Float, nullable=True)
    daily_return = Column(Float, nullable=True)

    benchmark_symbol = Column(String, nullable=False, default="510300")
    benchmark_name = Column(String, nullable=False, default="沪深300ETF")
    benchmark_price = Column(Float, nullable=True)
    benchmark_daily_return = Column(Float, nullable=True)

    real_market_value = Column(Float, nullable=True)
    source_system = Column(String, nullable=False, default="panwatch")
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WealthSnapshotItem(Base):
    """快照的分类明细。"""

    __tablename__ = "wealth_snapshot_items"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "category",
            name="uq_wealth_snapshot_item_category",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(Integer, nullable=False, index=True)
    category = Column(String, nullable=False)
    value_cny = Column(Float, nullable=False, default=0.0)
    exposure_cny = Column(Float, nullable=False, default=0.0)


class WealthSyncRun(Base):
    """外部同步审计记录，不保存同步密钥或完整原始持仓。"""

    __tablename__ = "wealth_sync_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_system = Column(String, nullable=False)
    status = Column(String, nullable=False)
    as_of_date = Column(String, nullable=False, default="")
    asset_count = Column(Integer, nullable=False, default=0)
    snapshot_count = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())
